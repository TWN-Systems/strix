import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import litellm
from jinja2 import (
    Environment,
    FileSystemLoader,
    select_autoescape,
)
from litellm import ModelResponse, completion_cost
from litellm.utils import supports_prompt_caching

from strix.llm.circuit_breaker import CircuitBreakerError, get_llm_circuit_breaker
from strix.llm.config import LLMConfig
from strix.llm.memory_compressor import MemoryCompressor
from strix.llm.request_queue import get_global_queue
from strix.llm.response_cache import get_global_cache
from strix.llm.utils import _truncate_to_first_function, parse_tool_invocations
from strix.prompts import load_prompt_modules
from strix.tools import get_tools_prompt


logger = logging.getLogger(__name__)


def _get_tracer() -> Any:
    """Get global tracer if available."""
    try:
        from strix.telemetry.tracer import get_global_tracer

        return get_global_tracer()
    except ImportError:
        return None

api_key = os.getenv("LLM_API_KEY")
if api_key:
    litellm.api_key = api_key

api_base = (
    os.getenv("LLM_API_BASE")
    or os.getenv("OPENAI_API_BASE")
    or os.getenv("LITELLM_BASE_URL")
    or os.getenv("OLLAMA_API_BASE")
)
if api_base:
    litellm.api_base = api_base


class LLMRequestFailedError(Exception):
    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


SUPPORTS_STOP_WORDS_FALSE_PATTERNS: list[str] = [
    "o1*",
    "grok-4-0709",
    "grok-code-fast-1",
    "deepseek-r1-0528*",
]

REASONING_EFFORT_PATTERNS: list[str] = [
    "o1-2024-12-17",
    "o1",
    "o3",
    "o3-2025-04-16",
    "o3-mini-2025-01-31",
    "o3-mini",
    "o4-mini",
    "o4-mini-2025-04-16",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gpt-5*",
    "deepseek-r1-0528*",
    "claude-sonnet-4-5*",
    "claude-haiku-4-5*",
]

# Retry configuration for transient errors
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0  # seconds
MAX_RETRY_DELAY = 16.0  # seconds

# Errors that are transient and should be retried
RETRYABLE_ERRORS = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
    litellm.APIConnectionError,
)


def normalize_model_name(model: str) -> str:
    raw = (model or "").strip().lower()
    if "/" in raw:
        name = raw.split("/")[-1]
        if ":" in name:
            name = name.split(":", 1)[0]
    else:
        name = raw
    if name.endswith("-gguf"):
        name = name[: -len("-gguf")]
    return name


def model_matches(model: str, patterns: list[str]) -> bool:
    raw = (model or "").strip().lower()
    name = normalize_model_name(model)
    for pat in patterns:
        pat_l = pat.lower()
        if "/" in pat_l:
            if fnmatch(raw, pat_l):
                return True
        elif fnmatch(name, pat_l):
            return True
    return False


class StepRole(str, Enum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


@dataclass
class LLMResponse:
    content: str
    tool_invocations: list[dict[str, Any]] | None = None
    scan_id: str | None = None
    step_number: int = 1
    role: StepRole = StepRole.AGENT


@dataclass
class RequestStats:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_creation_tokens: int = 0
    cost: float = 0.0
    requests: int = 0
    failed_requests: int = 0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost": round(self.cost, 4),
            "requests": self.requests,
            "failed_requests": self.failed_requests,
        }


class LLM:
    def __init__(
        self, config: LLMConfig, agent_name: str | None = None, agent_id: str | None = None
    ):
        self.config = config
        self.agent_name = agent_name
        self.agent_id = agent_id
        self._total_stats = RequestStats()
        self._last_request_stats = RequestStats()

        self.memory_compressor = MemoryCompressor(
            model_name=self.config.model_name,
            timeout=self.config.timeout,
        )

        if agent_name:
            prompt_dir = Path(__file__).parent.parent / "agents" / agent_name
            prompts_dir = Path(__file__).parent.parent / "prompts"

            loader = FileSystemLoader([prompt_dir, prompts_dir])
            self.jinja_env = Environment(
                loader=loader,
                autoescape=select_autoescape(enabled_extensions=(), default_for_string=False),
            )

            try:
                prompt_module_content = load_prompt_modules(
                    self.config.prompt_modules or [], self.jinja_env
                )

                def get_module(name: str) -> str:
                    return prompt_module_content.get(name, "")

                self.jinja_env.globals["get_module"] = get_module

                agent_role = self.config.agent_role

                def get_tools_prompt_with_role() -> str:
                    return get_tools_prompt(role=agent_role)

                self.system_prompt = self.jinja_env.get_template("system_prompt.jinja").render(
                    get_tools_prompt=get_tools_prompt_with_role,
                    loaded_module_names=list(prompt_module_content.keys()),
                    **prompt_module_content,
                )
            except (FileNotFoundError, OSError, ValueError) as e:
                logger.warning(f"Failed to load system prompt for {agent_name}: {e}")
                self.system_prompt = "You are a helpful AI assistant."
        else:
            self.system_prompt = "You are a helpful AI assistant."

    def set_agent_identity(self, agent_name: str | None, agent_id: str | None) -> None:
        if agent_name:
            self.agent_name = agent_name
        if agent_id:
            self.agent_id = agent_id

    def _build_identity_message(self) -> dict[str, Any] | None:
        if not (self.agent_name and str(self.agent_name).strip()):
            return None
        identity_name = self.agent_name
        identity_id = self.agent_id
        content = (
            "\n\n"
            "<agent_identity>\n"
            "<meta>Internal metadata: do not echo or reference; "
            "not part of history or tool calls.</meta>\n"
            "<note>You are now assuming the role of this agent. "
            "Act strictly as this agent and maintain self-identity for this step. "
            "Now go answer the next needed step!</note>\n"
            f"<agent_name>{identity_name}</agent_name>\n"
            f"<agent_id>{identity_id}</agent_id>\n"
            "</agent_identity>\n\n"
        )
        return {"role": "user", "content": content}

    def _add_cache_control_to_content(
        self, content: str | list[dict[str, Any]]
    ) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
        if isinstance(content, list) and content:
            last_item = content[-1]
            if isinstance(last_item, dict) and last_item.get("type") == "text":
                return content[:-1] + [{**last_item, "cache_control": {"type": "ephemeral"}}]
        return content

    def _is_anthropic_model(self) -> bool:
        if not self.config.model_name:
            return False
        model_lower = self.config.model_name.lower()
        return any(provider in model_lower for provider in ["anthropic/", "claude"])

    def _calculate_cache_interval(self, total_messages: int) -> int:
        if total_messages <= 1:
            return 10

        max_cached_messages = 3
        non_system_messages = total_messages - 1

        interval = 10
        while non_system_messages // interval > max_cached_messages:
            interval += 10

        return interval

    def _prepare_cached_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if (
            not self.config.enable_prompt_caching
            or not supports_prompt_caching(self.config.model_name)
            or not messages
        ):
            return messages

        if not self._is_anthropic_model():
            return messages

        cached_messages = list(messages)

        if cached_messages and cached_messages[0].get("role") == "system":
            system_message = cached_messages[0].copy()
            system_message["content"] = self._add_cache_control_to_content(
                system_message["content"]
            )
            cached_messages[0] = system_message

        total_messages = len(cached_messages)
        if total_messages > 1:
            interval = self._calculate_cache_interval(total_messages)

            cached_count = 0
            for i in range(interval, total_messages, interval):
                if cached_count >= 3:
                    break

                if i < len(cached_messages):
                    message = cached_messages[i].copy()
                    message["content"] = self._add_cache_control_to_content(message["content"])
                    cached_messages[i] = message
                    cached_count += 1

        return cached_messages

    async def generate(  # noqa: PLR0912, PLR0915
        self,
        conversation_history: list[dict[str, Any]],
        scan_id: str | None = None,
        step_number: int = 1,
    ) -> LLMResponse:
        messages = [{"role": "system", "content": self.system_prompt}]

        identity_message = self._build_identity_message()
        if identity_message:
            messages.append(identity_message)

        # Compress history (creates new list, doesn't mutate input)
        compressed_history = list(self.memory_compressor.compress_history(conversation_history))

        # Update caller's history in-place with compressed version
        # Note: This is intentional - it keeps agent's state.messages compressed
        if len(compressed_history) < len(conversation_history):
            conversation_history.clear()
            conversation_history.extend(compressed_history)

        messages.extend(compressed_history)

        cached_messages = self._prepare_cached_messages(messages)

        # Emit LLM request event
        tracer = _get_tracer()
        request_id = None
        start_time = time.time()

        if tracer and self.agent_id:
            request_id = tracer.log_llm_request(
                agent_id=self.agent_id,
                model=self.config.model_name,
            )

        # Check circuit breaker before attempting request
        circuit_breaker = get_llm_circuit_breaker()
        try:
            circuit_breaker.raise_if_open()
        except CircuitBreakerError as e:
            self._emit_llm_error(tracer, request_id, start_time, str(e), "CircuitBreakerError")
            raise LLMRequestFailedError(str(e), f"Retry in {e.time_until_retry:.1f}s") from e

        # Retry loop with exponential backoff for transient errors
        last_error: Exception | None = None
        retry_delay = INITIAL_RETRY_DELAY

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._make_request(cached_messages)
                self._update_usage_stats(response)

                # Record success with circuit breaker
                circuit_breaker.record_success()

                # Emit LLM response event
                duration_ms = (time.time() - start_time) * 1000
                if tracer and self.agent_id and request_id:
                    tracer.log_llm_response(
                        agent_id=self.agent_id,
                        request_id=request_id,
                        input_tokens=self._last_request_stats.input_tokens,
                        output_tokens=self._last_request_stats.output_tokens,
                        duration_ms=duration_ms,
                        cost=self._last_request_stats.cost,
                        cached_tokens=self._last_request_stats.cached_tokens,
                    )

                # Extract content with validation
                content = ""
                if not response.choices:
                    logger.warning("LLM returned empty choices, using empty content")
                elif (
                    hasattr(response.choices[0], "message")
                    and response.choices[0].message
                ):
                    content = getattr(response.choices[0].message, "content", "") or ""

                content = _truncate_to_first_function(content)

                if "</function>" in content:
                    function_end_index = content.find("</function>") + len("</function>")
                    content = content[:function_end_index]

                # Parse tool invocations with graceful degradation
                tool_invocations = None
                try:
                    tool_invocations = parse_tool_invocations(content)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Failed to parse tool invocations: {e}")
                    # Continue with None tool_invocations - agent will handle text response

                return LLMResponse(
                    scan_id=scan_id,
                    step_number=step_number,
                    role=StepRole.AGENT,
                    content=content,
                    tool_invocations=tool_invocations if tool_invocations else None,
                )

            except RETRYABLE_ERRORS as e:
                last_error = e
                error_type = type(e).__name__

                # Record failure with circuit breaker (transient errors count)
                circuit_breaker.record_failure(e)

                if attempt < MAX_RETRIES:
                    # Log retry attempt
                    logger.warning(
                        f"LLM request failed ({error_type}), retrying in {retry_delay}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                    continue

                # All retries exhausted
                self._emit_llm_error(
                    tracer, request_id, start_time,
                    f"{error_type} (after {MAX_RETRIES} retries)",
                    error_type, str(e)
                )
                raise LLMRequestFailedError(
                    f"LLM request failed: {error_type} (after {MAX_RETRIES} retries)",
                    str(e)
                ) from e

            except (
                litellm.AuthenticationError,
                litellm.NotFoundError,
                litellm.ContextWindowExceededError,
                litellm.ContentPolicyViolationError,
                litellm.BudgetExceededError,
                litellm.UnsupportedParamsError,
                litellm.InvalidRequestError,
                litellm.BadRequestError,
            ) as e:
                # Non-retryable errors - fail immediately (don't affect circuit breaker)
                error_type = type(e).__name__
                error_msg = self._get_error_message(e)
                self._emit_llm_error(tracer, request_id, start_time, error_msg, error_type, str(e))
                raise LLMRequestFailedError(f"LLM request failed: {error_msg}", str(e)) from e

            except Exception as e:
                # Unknown errors - record with circuit breaker and fail
                circuit_breaker.record_failure(e)
                error_type = type(e).__name__
                self._emit_llm_error(tracer, request_id, start_time, str(e), error_type, str(e))
                raise LLMRequestFailedError(f"LLM request failed: {error_type}", str(e)) from e

        # Should not reach here, but handle edge case
        if last_error:
            raise LLMRequestFailedError(
                f"LLM request failed after {MAX_RETRIES} retries",
                str(last_error)
            ) from last_error
        raise LLMRequestFailedError("LLM request failed: Unknown error")

    def _emit_llm_error(
        self, tracer: Any, request_id: str | None, start_time: float, error: str,
        error_type: str | None = None, details: str | None = None
    ) -> None:
        """Emit LLM error event to tracer with full details."""
        if tracer and self.agent_id and request_id:
            duration_ms = (time.time() - start_time) * 1000
            # Build detailed error message
            error_parts = [error]
            if error_type:
                error_parts.insert(0, f"[{error_type}]")
            if details:
                # Truncate very long details but keep useful info
                if len(details) > 500:
                    details = details[:500] + "..."
                error_parts.append(f"\nDetails: {details}")

            full_error = " ".join(error_parts) if error_type else error
            if details:
                full_error = f"{full_error}\nDetails: {details}"

            tracer.log_llm_error(
                agent_id=self.agent_id,
                request_id=request_id,
                error=full_error,
                duration_ms=duration_ms,
            )

    def _get_error_message(self, error: Exception) -> str:
        """Get human-readable error message for common LiteLLM errors."""
        error_messages = {
            "AuthenticationError": "Invalid API key",
            "NotFoundError": "Model not found",
            "ContextWindowExceededError": "Context too long",
            "ContentPolicyViolationError": "Content policy violation",
            "BudgetExceededError": "Budget exceeded",
            "UnsupportedParamsError": "Unsupported parameters",
            "InvalidRequestError": "Invalid request",
            "BadRequestError": "Bad request",
        }
        error_type = type(error).__name__
        return error_messages.get(error_type, error_type)

    @property
    def usage_stats(self) -> dict[str, dict[str, int | float]]:
        return {
            "total": self._total_stats.to_dict(),
            "last_request": self._last_request_stats.to_dict(),
        }

    def get_cache_config(self) -> dict[str, bool]:
        return {
            "enabled": self.config.enable_prompt_caching,
            "supported": supports_prompt_caching(self.config.model_name),
        }

    def _should_include_stop_param(self) -> bool:
        if not self.config.model_name:
            return True

        return not model_matches(self.config.model_name, SUPPORTS_STOP_WORDS_FALSE_PATTERNS)

    def _should_include_reasoning_effort(self) -> bool:
        if not self.config.model_name:
            return False

        return model_matches(self.config.model_name, REASONING_EFFORT_PATTERNS)

    def _should_use_streaming(self) -> bool:
        """Check if streaming should be used for this request."""
        if not self.config.enable_streaming:
            return False

        # Some models don't support streaming well
        if not self.config.model_name:
            return False

        # Disable streaming for reasoning models (they often don't support it well)
        model_lower = self.config.model_name.lower()
        no_stream_patterns = ["o1", "o3", "o4"]
        if any(pat in model_lower for pat in no_stream_patterns):
            return False

        return True

    async def _make_request(
        self,
        messages: list[dict[str, Any]],
    ) -> ModelResponse:
        completion_args: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "timeout": self.config.timeout,
        }

        if self._should_include_stop_param():
            completion_args["stop"] = ["</function>"]

        if self._should_include_reasoning_effort():
            completion_args["reasoning_effort"] = "high"

        # Check cache first
        cache = get_global_cache()
        cached_response = cache.get(
            model=completion_args["model"],
            messages=completion_args["messages"],
        )
        if cached_response is not None:
            logger.debug("Using cached LLM response")
            self._total_stats.requests += 1
            self._last_request_stats = RequestStats(requests=1)
            return cached_response

        queue = get_global_queue()

        if self._should_use_streaming():
            response = await self._make_streaming_request(queue, completion_args)
        else:
            response = await queue.make_request(completion_args)

        # Cache the response
        cache.put(
            model=completion_args["model"],
            messages=completion_args["messages"],
            response=response,
        )

        self._total_stats.requests += 1
        self._last_request_stats = RequestStats(requests=1)

        return response

    async def _make_streaming_request(
        self,
        queue: Any,
        completion_args: dict[str, Any],
    ) -> ModelResponse:
        """Make a streaming request with early termination on </function> tag."""

        def stop_on_function_end(content: str) -> bool:
            return "</function>" in content

        content, usage_chunk = await queue.make_streaming_request(
            completion_args,
            on_chunk=None,  # Could add callback for real-time display
            stop_condition=stop_on_function_end,
        )

        # Build a synthetic ModelResponse from streamed content
        # This maintains compatibility with the rest of the code
        from litellm import ModelResponse as LiteLLMResponse
        from litellm.utils import Usage, Choices, Message

        message = Message(content=content, role="assistant")
        choice = Choices(index=0, message=message, finish_reason="stop")

        # Use usage from final chunk if available, otherwise estimate
        if usage_chunk and hasattr(usage_chunk, "usage") and usage_chunk.usage:
            usage = usage_chunk.usage
        else:
            # Estimate tokens (rough approximation)
            usage = Usage(
                prompt_tokens=0,  # Will be updated from actual response
                completion_tokens=len(content) // 4,  # ~4 chars per token
                total_tokens=len(content) // 4,
            )

        response = LiteLLMResponse(
            id="stream-" + str(time.time()),
            choices=[choice],
            created=int(time.time()),
            model=self.config.model_name,
            usage=usage,
        )

        return response

    def _update_usage_stats(self, response: ModelResponse) -> None:
        try:
            if hasattr(response, "usage") and response.usage:
                input_tokens = getattr(response.usage, "prompt_tokens", 0)
                output_tokens = getattr(response.usage, "completion_tokens", 0)

                cached_tokens = 0
                cache_creation_tokens = 0

                if hasattr(response.usage, "prompt_tokens_details"):
                    prompt_details = response.usage.prompt_tokens_details
                    if hasattr(prompt_details, "cached_tokens"):
                        cached_tokens = prompt_details.cached_tokens or 0

                if hasattr(response.usage, "cache_creation_input_tokens"):
                    cache_creation_tokens = response.usage.cache_creation_input_tokens or 0

            else:
                input_tokens = 0
                output_tokens = 0
                cached_tokens = 0
                cache_creation_tokens = 0

            try:
                cost = completion_cost(response) or 0.0
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to calculate cost: {e}")
                cost = 0.0

            self._total_stats.input_tokens += input_tokens
            self._total_stats.output_tokens += output_tokens
            self._total_stats.cached_tokens += cached_tokens
            self._total_stats.cache_creation_tokens += cache_creation_tokens
            self._total_stats.cost += cost

            self._last_request_stats.input_tokens = input_tokens
            self._last_request_stats.output_tokens = output_tokens
            self._last_request_stats.cached_tokens = cached_tokens
            self._last_request_stats.cache_creation_tokens = cache_creation_tokens
            self._last_request_stats.cost = cost

            if cached_tokens > 0:
                logger.info(f"Cache hit: {cached_tokens} cached tokens, {input_tokens} new tokens")
            if cache_creation_tokens > 0:
                logger.info(f"Cache creation: {cache_creation_tokens} tokens written to cache")

            logger.info(f"Usage stats: {self.usage_stats}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to update usage stats: {e}")
