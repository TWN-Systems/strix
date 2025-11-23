from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from multiprocessing import Process, Queue
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError


SANDBOX_MODE = os.getenv("STRIX_SANDBOX_MODE", "false").lower() == "true"
if not SANDBOX_MODE:
    raise RuntimeError("Tool server should only run in sandbox mode (STRIX_SANDBOX_MODE=true)")

parser = argparse.ArgumentParser(description="Start Strix tool server")
parser.add_argument("--token", required=True, help="Authentication token")
parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")  # nosec
parser.add_argument("--port", type=int, required=True, help="Port to bind to")

args = parser.parse_args()
EXPECTED_TOKEN = args.token

app = FastAPI()
security = HTTPBearer()

security_dependency = Depends(security)

agent_processes: dict[str, dict[str, Any]] = {}
agent_queues: dict[str, dict[str, Queue[Any]]] = {}


def verify_token(credentials: HTTPAuthorizationCredentials) -> str:
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != EXPECTED_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials


class ToolExecutionRequest(BaseModel):
    agent_id: str
    tool_name: str
    kwargs: dict[str, Any]


class ToolExecutionResponse(BaseModel):
    result: Any | None = None
    error: str | None = None


QUEUE_TIMEOUT = 120  # 2 minutes timeout for queue operations


def agent_worker(_agent_id: str, request_queue: Queue[Any], response_queue: Queue[Any]) -> None:
    import os
    from pathlib import Path
    from queue import Empty

    # Configure file-based logging for worker process (instead of suppressing)
    log_dir = Path("/tmp/strix_workers")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"worker_{os.getpid()}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers = [file_handler]
    root_logger.setLevel(logging.WARNING)

    from strix.tools.argument_parser import ArgumentConversionError, convert_arguments
    from strix.tools.registry import get_tool_by_name

    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            # Use timeout to prevent infinite blocking
            try:
                request = request_queue.get(timeout=QUEUE_TIMEOUT)
            except Empty:
                continue  # Keep worker alive, just no request received

            if request is None:
                break

            tool_name = request["tool_name"]
            kwargs = request["kwargs"]

            try:
                tool_func = get_tool_by_name(tool_name)
                if not tool_func:
                    response_queue.put({"error": f"Tool '{tool_name}' not found"})
                    continue

                converted_kwargs = convert_arguments(tool_func, kwargs)
                result = tool_func(**converted_kwargs)

                response_queue.put({"result": result})
                consecutive_errors = 0  # Reset on success

            except (ArgumentConversionError, ValidationError) as e:
                response_queue.put({"error": f"Invalid arguments: {e}"})
            except (RuntimeError, ValueError, ImportError) as e:
                response_queue.put({"error": f"Tool execution error: {e}"})
            except Exception as e:  # noqa: BLE001
                # Catch-all for unexpected errors
                consecutive_errors += 1
                response_queue.put({"error": f"Unexpected error ({type(e).__name__}): {e}"})
                if consecutive_errors >= max_consecutive_errors:
                    response_queue.put({"error": "Worker terminating due to repeated errors"})
                    break

        except Exception as e:  # noqa: BLE001
            # Critical error in worker loop itself
            try:
                response_queue.put({"error": f"Critical worker error: {e}"})
            except Exception:  # noqa: BLE001
                pass  # Queue might be broken
            break  # Exit worker on critical errors


def _create_agent_process(agent_id: str) -> tuple[Queue[Any], Queue[Any]]:
    """Create a new worker process for an agent."""
    request_queue: Queue[Any] = Queue()
    response_queue: Queue[Any] = Queue()

    process = Process(
        target=agent_worker, args=(agent_id, request_queue, response_queue), daemon=True
    )
    process.start()

    agent_processes[agent_id] = {"process": process, "pid": process.pid}
    agent_queues[agent_id] = {"request": request_queue, "response": response_queue}

    return request_queue, response_queue


def _cleanup_dead_process(agent_id: str) -> None:
    """Clean up resources for a dead worker process."""
    if agent_id in agent_processes:
        try:
            process = agent_processes[agent_id]["process"]
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        del agent_processes[agent_id]

    if agent_id in agent_queues:
        del agent_queues[agent_id]


def ensure_agent_process(agent_id: str) -> tuple[Queue[Any], Queue[Any]]:
    """Ensure a healthy worker process exists for the agent, restarting if needed."""
    if agent_id in agent_processes:
        process = agent_processes[agent_id]["process"]
        if not process.is_alive():
            # Process died, clean up and restart
            logging.getLogger(__name__).warning(
                f"Agent worker {agent_id} (pid {agent_processes[agent_id]['pid']}) died, restarting"
            )
            _cleanup_dead_process(agent_id)
            return _create_agent_process(agent_id)

        return agent_queues[agent_id]["request"], agent_queues[agent_id]["response"]

    return _create_agent_process(agent_id)


RESPONSE_TIMEOUT = 180  # 3 minutes max wait for tool response


@app.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(
    request: ToolExecutionRequest, credentials: HTTPAuthorizationCredentials = security_dependency
) -> ToolExecutionResponse:
    verify_token(credentials)

    request_queue, response_queue = ensure_agent_process(request.agent_id)

    request_queue.put({"tool_name": request.tool_name, "kwargs": request.kwargs})

    try:
        loop = asyncio.get_event_loop()

        # Use timeout to prevent indefinite blocking
        def get_response_with_timeout() -> dict[str, Any]:
            from queue import Empty
            try:
                return response_queue.get(timeout=RESPONSE_TIMEOUT)
            except Empty:
                return {"error": f"Tool execution timed out after {RESPONSE_TIMEOUT}s"}

        response = await loop.run_in_executor(None, get_response_with_timeout)

        if "error" in response:
            return ToolExecutionResponse(error=response["error"])
        return ToolExecutionResponse(result=response.get("result"))

    except (RuntimeError, ValueError, OSError) as e:
        return ToolExecutionResponse(error=f"Worker error: {e}")
    except Exception as e:  # noqa: BLE001
        return ToolExecutionResponse(error=f"Unexpected error: {type(e).__name__}: {e}")


@app.post("/register_agent")
async def register_agent(
    agent_id: str, credentials: HTTPAuthorizationCredentials = security_dependency
) -> dict[str, str]:
    verify_token(credentials)

    ensure_agent_process(agent_id)
    return {"status": "registered", "agent_id": agent_id}


@app.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "healthy",
        "sandbox_mode": str(SANDBOX_MODE),
        "environment": "sandbox" if SANDBOX_MODE else "main",
        "auth_configured": "true" if EXPECTED_TOKEN else "false",
        "active_agents": len(agent_processes),
        "agents": list(agent_processes.keys()),
    }


def cleanup_all_agents() -> None:
    for agent_id in list(agent_processes.keys()):
        try:
            agent_queues[agent_id]["request"].put(None)
            process = agent_processes[agent_id]["process"]

            process.join(timeout=1)

            if process.is_alive():
                process.terminate()
                process.join(timeout=1)

            if process.is_alive():
                process.kill()

        except (BrokenPipeError, EOFError, OSError):
            pass
        except (RuntimeError, ValueError) as e:
            logging.getLogger(__name__).debug(f"Error during agent cleanup: {e}")


def signal_handler(_signum: int, _frame: Any) -> None:
    signal.signal(signal.SIGPIPE, signal.SIG_IGN) if hasattr(signal, "SIGPIPE") else None
    cleanup_all_agents()
    sys.exit(0)


if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        cleanup_all_agents()
