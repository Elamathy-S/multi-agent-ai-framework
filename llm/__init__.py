"""
llm — provider-neutral LLM access.

    from llm import get_llm
    llm = get_llm()          # LLM_PROVIDER=anthropic (default) | gemini | ollama | openai_compat
"""

from dotenv import load_dotenv

load_dotenv()          # read .env so LLM_PROVIDER / API keys are picked up

import os

from llm.types import (  # noqa: F401
    LLMClient, LLMError, LLMResponse, ToolCall, ToolResult, ToolSpec, Usage,
)


def get_llm() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        from llm.anthropic_client import AnthropicClient
        return AnthropicClient()
    if provider == "ollama":
        from llm.ollama_client import OllamaClient
        return OllamaClient()
    if provider == "gemini":
        from llm.openai_compat import OpenAICompatClient
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey")
        return OpenAICompatClient(
            name="Gemini", api_key=key,
            base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            model=os.getenv("LLM_MODEL", "gemini-3.8-flash"),
            reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "low"),   # Gemini 3 always thinks; keep it short
            min_output_tokens=4096,                                      # thinking tokens count against the limit
            gemini_signatures=True,
        )
    if provider == "openai_compat":
        from llm.openai_compat import OpenAICompatClient
        missing = [v for v in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if not os.getenv(v)]
        if missing:
            raise LLMError(f"LLM_PROVIDER=openai_compat needs: {', '.join(missing)}")
        return OpenAICompatClient(
            name="LLM", base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
            model=os.environ["LLM_MODEL"], reasoning_effort=os.getenv("LLM_REASONING_EFFORT") or None,
        )
    raise LLMError(f"Unknown LLM_PROVIDER '{provider}' (use anthropic, gemini, ollama or openai_compat)")