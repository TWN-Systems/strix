import os


class LLMConfig:
    def __init__(
        self,
        model_name: str | None = None,
        enable_prompt_caching: bool = True,
        prompt_modules: list[str] | None = None,
        timeout: int | None = None,
        agent_role: str | None = None,
        enable_streaming: bool | None = None,
    ):
        self.model_name = model_name or os.getenv("STRIX_LLM", "openai/gpt-5")

        if not self.model_name:
            raise ValueError("STRIX_LLM environment variable must be set and not empty")

        self.enable_prompt_caching = enable_prompt_caching
        self.prompt_modules = prompt_modules or []
        self.agent_role = agent_role

        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", "600"))

        # Streaming enabled by default, can be disabled via env var
        if enable_streaming is not None:
            self.enable_streaming = enable_streaming
        else:
            self.enable_streaming = os.getenv("LLM_STREAMING", "true").lower() == "true"
