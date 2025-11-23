"""Circuit breaker pattern for LLM API calls.

Prevents cascading failures when LLM API is unavailable by
failing fast after repeated failures.
"""

import logging
import os
import threading
import time
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, time_until_retry: float):
        super().__init__(message)
        self.time_until_retry = time_until_retry


class CircuitBreaker:
    """Thread-safe circuit breaker for protecting external service calls."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        recovery_timeout: float | None = None,
        half_open_max_calls: int = 1,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold or int(
            os.environ.get("LLM_CIRCUIT_FAILURE_THRESHOLD", "5")
        )
        self.recovery_timeout = recovery_timeout or float(
            os.environ.get("LLM_CIRCUIT_RECOVERY_TIMEOUT", "60")
        )
        self.half_open_max_calls = half_open_max_calls
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

        # Stats
        self._total_calls = 0
        self._total_failures = 0
        self._total_circuit_breaks = 0

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, updating if recovery timeout has passed."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"Circuit breaker '{self.name}' entering half-open state")
            return self._state

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout

    def _time_until_recovery(self) -> float:
        """Get seconds until circuit breaker will attempt recovery."""
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    def can_execute(self) -> bool:
        """Check if a call can be executed."""
        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True

        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                return self._half_open_calls < self.half_open_max_calls

        return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._total_calls += 1

            if self._state == CircuitState.HALF_OPEN:
                # Recovery successful, close circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info(f"Circuit breaker '{self.name}' recovered, closing circuit")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed call."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Recovery failed, reopen circuit
                self._state = CircuitState.OPEN
                self._total_circuit_breaks += 1
                logger.warning(
                    f"Circuit breaker '{self.name}' recovery failed, reopening circuit"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._total_circuit_breaks += 1
                    logger.warning(
                        f"Circuit breaker '{self.name}' opened after {self._failure_count} failures"
                    )

    def raise_if_open(self) -> None:
        """Raise CircuitBreakerError if circuit is open."""
        if not self.can_execute():
            time_until_retry = self._time_until_recovery()
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is open. Service unavailable. "
                f"Retry in {time_until_retry:.1f}s",
                time_until_retry=time_until_retry,
            )

        # Track half-open calls
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            logger.info(f"Circuit breaker '{self.name}' manually reset")

    @property
    def stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "total_calls": self._total_calls,
                "total_failures": self._total_failures,
                "total_circuit_breaks": self._total_circuit_breaks,
                "time_until_recovery": self._time_until_recovery() if self._state == CircuitState.OPEN else 0,
            }


# Global circuit breaker for LLM API
_llm_circuit_breaker: CircuitBreaker | None = None


def get_llm_circuit_breaker() -> CircuitBreaker:
    """Get the global LLM circuit breaker instance."""
    global _llm_circuit_breaker  # noqa: PLW0603
    if _llm_circuit_breaker is None:
        _llm_circuit_breaker = CircuitBreaker(name="llm_api")
    return _llm_circuit_breaker
