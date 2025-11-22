import os

import litellm

from .config import LLMConfig
from .llm import LLM, LLMRequestFailedError


__all__ = [
    "LLM",
    "LLMConfig",
    "LLMRequestFailedError",
]

# Only disable debugging if not in debug mode
# Debug mode is enabled via --debug flag or STRIX_DEBUG env var
if os.getenv("STRIX_DEBUG", "").lower() != "true":
    litellm._logging._disable_debugging()

litellm.drop_params = True
