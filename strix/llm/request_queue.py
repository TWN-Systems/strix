import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import litellm
from litellm import ModelResponse, completion
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    """Tracks rate limit status across the queue."""

    is_rate_limited: bool = False
    rate_limit_start: datetime | None = None
    retry_attempt: int = 0
    max_retry_attempts: int = 7
    consecutive_rate_limits: int = 0
    last_rate_limit_error: str | None = None
    total_rate_limit_hits: int = 0


@dataclass
class QueueStats:
    """Statistics for the request queue."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0
    total_retry_attempts: int = 0
    average_wait_time: float = 0.0
    _wait_times: list[float] = field(default_factory=list)

    def record_wait_time(self, wait_time: float) -> None:
        self._wait_times.append(wait_time)
        self.average_wait_time = sum(self._wait_times) / len(self._wait_times)


def should_retry_exception(exception: Exception) -> bool:
    status_code = None

    if hasattr(exception, "status_code"):
        status_code = exception.status_code
    elif hasattr(exception, "response") and hasattr(exception.response, "status_code"):
        status_code = exception.response.status_code

    if status_code is not None:
        return bool(litellm._should_retry(status_code))
    return True


def is_rate_limit_error(exception: Exception) -> bool:
    """Check if the exception is a rate limit error."""
    if isinstance(exception, litellm.RateLimitError):
        return True

    status_code = None
    if hasattr(exception, "status_code"):
        status_code = exception.status_code
    elif hasattr(exception, "response") and hasattr(exception.response, "status_code"):
        status_code = exception.response.status_code

    return status_code == 429


class LLMRequestQueue:
    def __init__(self, max_concurrent: int = 6, delay_between_requests: float = 5.0):
        rate_limit_delay = os.getenv("LLM_RATE_LIMIT_DELAY")
        if rate_limit_delay:
            delay_between_requests = float(rate_limit_delay)

        rate_limit_concurrent = os.getenv("LLM_RATE_LIMIT_CONCURRENT")
        if rate_limit_concurrent:
            max_concurrent = int(rate_limit_concurrent)

        self.max_concurrent = max_concurrent
        self.delay_between_requests = delay_between_requests
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._last_request_time = 0.0
        self._lock = threading.Lock()

        self.rate_limit_state = RateLimitState()
        self.stats = QueueStats()
        self._rate_limit_backoff_multiplier = 2.0

    async def make_request(self, completion_args: dict[str, Any]) -> ModelResponse:
        self.stats.total_requests += 1
        start_time = time.time()

        try:
            while not self._semaphore.acquire(timeout=0.2):
                await asyncio.sleep(0.1)

            if self.rate_limit_state.is_rate_limited:
                extra_delay = self._calculate_rate_limit_delay()
                if extra_delay > 0:
                    logger.info(f"Rate limit active, waiting additional {extra_delay:.1f}s")
                    await asyncio.sleep(extra_delay)

            with self._lock:
                now = time.time()
                time_since_last = now - self._last_request_time
                sleep_needed = max(0, self.delay_between_requests - time_since_last)
                self._last_request_time = now + sleep_needed

            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)
                self.stats.record_wait_time(sleep_needed)

            result = await self._reliable_request(completion_args)

            self.stats.successful_requests += 1
            self._clear_rate_limit_state()

            return result

        except Exception as e:
            self.stats.failed_requests += 1
            if is_rate_limit_error(e):
                self._handle_rate_limit_error(e)
            raise
        finally:
            self._semaphore.release()

    def _calculate_rate_limit_delay(self) -> float:
        """Calculate additional delay when rate limited."""
        if not self.rate_limit_state.is_rate_limited:
            return 0.0

        base_delay = 30.0
        multiplier = min(self.rate_limit_state.consecutive_rate_limits, 5)
        return base_delay * (self._rate_limit_backoff_multiplier ** multiplier)

    def _handle_rate_limit_error(self, exception: Exception) -> None:
        """Update state when a rate limit error occurs."""
        with self._lock:
            self.rate_limit_state.is_rate_limited = True
            self.rate_limit_state.rate_limit_start = datetime.now(UTC)
            self.rate_limit_state.consecutive_rate_limits += 1
            self.rate_limit_state.total_rate_limit_hits += 1
            self.rate_limit_state.last_rate_limit_error = str(exception)
            self.stats.rate_limited_requests += 1

            logger.warning(
                f"Rate limit hit (consecutive: {self.rate_limit_state.consecutive_rate_limits}, "
                f"total: {self.rate_limit_state.total_rate_limit_hits})"
            )

    def _clear_rate_limit_state(self) -> None:
        """Clear rate limit state after successful request."""
        with self._lock:
            if self.rate_limit_state.is_rate_limited:
                logger.info("Rate limit cleared after successful request")
            self.rate_limit_state.is_rate_limited = False
            self.rate_limit_state.rate_limit_start = None
            self.rate_limit_state.retry_attempt = 0
            self.rate_limit_state.consecutive_rate_limits = 0

    def _on_retry(self, retry_state: RetryCallState) -> None:
        """Callback when a retry is about to happen."""
        self.stats.total_retry_attempts += 1
        self.rate_limit_state.retry_attempt = retry_state.attempt_number

        exception = retry_state.outcome.exception() if retry_state.outcome else None
        if exception and is_rate_limit_error(exception):
            self._handle_rate_limit_error(exception)

        logger.info(
            f"Retry attempt {retry_state.attempt_number}/{self.rate_limit_state.max_retry_attempts} "
            f"after {retry_state.seconds_since_start:.1f}s"
        )

    def is_retrying(self) -> bool:
        """Check if the queue is currently in a retry loop."""
        return self.rate_limit_state.retry_attempt > 0

    def get_rate_limit_info(self) -> dict[str, Any]:
        """Get current rate limit information."""
        return {
            "is_rate_limited": self.rate_limit_state.is_rate_limited,
            "consecutive_rate_limits": self.rate_limit_state.consecutive_rate_limits,
            "total_rate_limit_hits": self.rate_limit_state.total_rate_limit_hits,
            "current_retry_attempt": self.rate_limit_state.retry_attempt,
            "is_retrying": self.is_retrying(),
        }

    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(7),
        wait=wait_exponential(multiplier=6, min=12, max=150),
        retry=retry_if_exception(should_retry_exception),
        reraise=True,
    )
    async def _reliable_request(self, completion_args: dict[str, Any]) -> ModelResponse:
        response = completion(**completion_args, stream=False)
        if isinstance(response, ModelResponse):
            return response
        self._raise_unexpected_response()
        raise RuntimeError("Unreachable code")

    def _raise_unexpected_response(self) -> None:
        raise RuntimeError("Unexpected response type")

    def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        return {
            "total_requests": self.stats.total_requests,
            "successful_requests": self.stats.successful_requests,
            "failed_requests": self.stats.failed_requests,
            "rate_limited_requests": self.stats.rate_limited_requests,
            "total_retry_attempts": self.stats.total_retry_attempts,
            "average_wait_time": round(self.stats.average_wait_time, 2),
            "success_rate": round(
                self.stats.successful_requests / max(1, self.stats.total_requests) * 100, 1
            ),
        }


_global_queue: LLMRequestQueue | None = None


def get_global_queue() -> LLMRequestQueue:
    global _global_queue  # noqa: PLW0603
    if _global_queue is None:
        _global_queue = LLMRequestQueue()
    return _global_queue
