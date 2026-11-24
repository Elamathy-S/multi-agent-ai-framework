"""
llm — provider-neutral LLM access.

    from llm import get_llm
    llm = get_llm()          # LLM_PROVIDER=anthropic (default) | ollama
"""

import os

from llm.types import (  # noqa: F401
    LLMClient, LLMError, LLMResponse, ToolCall, ToolResult, ToolSpec, Usage,
)

from dotenv import load_dotenv

load_dotenv()


def get_llm() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        from llm.anthropic_client import AnthropicClient
        return AnthropicClient()
    if provider == "ollama":
        from llm.ollama_client import OllamaClient
        return OllamaClient()
    raise LLMError(f"Unknown LLM_PROVIDER '{provider}' (use 'anthropic' or 'ollama')")
