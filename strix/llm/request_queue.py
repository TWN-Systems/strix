import asyncio
import logging
import os
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import litellm
from litellm import ModelResponse, completion
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


logger = logging.getLogger(__name__)


def should_retry_exception(exception: Exception) -> bool:
    status_code = None

    if hasattr(exception, "status_code"):
        status_code = exception.status_code
    elif hasattr(exception, "response") and hasattr(exception.response, "status_code"):
        status_code = exception.response.status_code

    if status_code is not None:
        return bool(litellm._should_retry(status_code))
    return True


class LLMRequestQueue:
    def __init__(self, max_concurrent: int | None = None, delay_between_requests: float | None = None):
        self.max_concurrent = max_concurrent or int(os.environ.get("LLM_RATE_LIMIT_CONCURRENT", "6"))
        self.delay_between_requests = delay_between_requests or float(
            os.environ.get("LLM_RATE_LIMIT_DELAY", "1.0")
        )
        # Use threading primitives - they work across all event loops
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)
        self._last_request_time = 0.0
        self._lock = threading.Lock()

    async def _acquire_slot(self) -> float:
        """Acquire a request slot and return the sleep time needed."""
        self._semaphore.acquire()
        with self._lock:
            now = time.time()
            time_since_last = now - self._last_request_time
            sleep_needed = max(0, self.delay_between_requests - time_since_last)
            self._last_request_time = now + sleep_needed
        return sleep_needed

    def _release_slot(self) -> None:
        """Release the request slot."""
        self._semaphore.release()

    async def make_request(self, completion_args: dict[str, Any]) -> ModelResponse:
        sleep_needed = await self._acquire_slot()
        try:
            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)

            return await self._reliable_request(completion_args)
        finally:
            self._release_slot()

    async def make_streaming_request(
        self,
        completion_args: dict[str, Any],
        on_chunk: Callable[[str], None] | None = None,
        stop_condition: Callable[[str], bool] | None = None,
    ) -> tuple[str, ModelResponse | None]:
        """Make a streaming request, accumulating content and optionally stopping early.

        Args:
            completion_args: Arguments to pass to litellm completion
            on_chunk: Optional callback for each content chunk
            stop_condition: Optional function that returns True to stop streaming early

        Returns:
            Tuple of (accumulated_content, final_response_with_usage_or_None)
        """
        sleep_needed = await self._acquire_slot()
        try:
            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)

            return await self._streaming_request(completion_args, on_chunk, stop_condition)
        finally:
            self._release_slot()

    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=1, max=30),
        retry=retry_if_exception(should_retry_exception),
        reraise=True,
    )
    async def _reliable_request(self, completion_args: dict[str, Any]) -> ModelResponse:
        response = completion(**completion_args, stream=False)
        if isinstance(response, ModelResponse):
            return response
        self._raise_unexpected_response()
        raise RuntimeError("Unreachable code")

    async def _streaming_request(
        self,
        completion_args: dict[str, Any],
        on_chunk: Callable[[str], None] | None = None,
        stop_condition: Callable[[str], bool] | None = None,
    ) -> tuple[str, ModelResponse | None]:
        """Execute streaming request with early termination support."""
        accumulated_content = ""
        final_response: ModelResponse | None = None

        # Start streaming
        stream = completion(**completion_args, stream=True)

        try:
            async for chunk in self._iter_stream(stream):
                # Extract content from chunk
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = getattr(chunk.choices[0], "delta", None)
                    if delta:
                        content = getattr(delta, "content", None)
                        if content:
                            accumulated_content += content
                            if on_chunk:
                                on_chunk(content)

                            # Check for early termination
                            if stop_condition and stop_condition(accumulated_content):
                                logger.debug("Streaming stopped early due to stop condition")
                                break

                # Capture usage from final chunk if available
                if hasattr(chunk, "usage") and chunk.usage:
                    final_response = chunk

        except GeneratorExit:
            pass

        return accumulated_content, final_response

    async def _iter_stream(self, stream: Any) -> AsyncIterator[Any]:
        """Iterate over stream, handling both sync and async generators."""
        if hasattr(stream, "__anext__"):
            # Async generator
            async for chunk in stream:
                yield chunk
        else:
            # Sync generator - wrap in async
            for chunk in stream:
                yield chunk
                # Yield control to event loop periodically
                await asyncio.sleep(0)

    def _raise_unexpected_response(self) -> None:
        raise RuntimeError("Unexpected response type")


_global_queue: LLMRequestQueue | None = None


def get_global_queue() -> LLMRequestQueue:
    global _global_queue  # noqa: PLW0603
    if _global_queue is None:
        _global_queue = LLMRequestQueue()
    return _global_queue
