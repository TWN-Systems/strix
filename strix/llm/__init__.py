import os

import litellm

from .circuit_breaker import CircuitBreaker, CircuitBreakerError, get_llm_circuit_breaker
from .config import LLMConfig
from .llm import LLM, LLMRequestFailedError
from .response_cache import ResponseCache, get_global_cache


__all__ = [
    "LLM",
    "LLMConfig",
    "LLMRequestFailedError",
    "CircuitBreaker",
    "CircuitBreakerError",
    "get_llm_circuit_breaker",
    "ResponseCache",
    "get_global_cache",
]

# Only disable debugging if not in debug mode
# Debug mode is enabled via --debug flag or STRIX_DEBUG env var
if os.getenv("STRIX_DEBUG", "").lower() != "true":
    litellm._logging._disable_debugging()

litellm.drop_params = True
