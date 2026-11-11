"""
Factory that returns the right LLM client based on the LLM_PROVIDER env var.

Supported values for LLM_PROVIDER:
  gemini        – Google Gemini via google-genai SDK (default)
  openai        – OpenAI chat completions API
  azure_openai  – Azure OpenAI chat completions API
    ollama        – Local or in-cluster Ollama HTTP API
"""

from app.config import Settings
from app.exceptions import LLMClientError


def create_llm_client(settings: Settings) -> object:
    """Instantiate and return the configured LLM provider client."""
    provider = settings.llm_provider.lower().strip()

    if provider == "openai":
        from app.openai_client import OpenAIClient
        return OpenAIClient(settings)

    if provider in ("azure_openai", "azure"):
        from app.openai_client import AzureOpenAIClient
        return AzureOpenAIClient(settings)

    if provider == "ollama":
        from app.ollama_client import OllamaClient
        return OllamaClient(settings)

    # default: gemini
    from app.gemini_client import GeminiClient
    return GeminiClient(settings)


__all__ = ["LLMClientError", "create_llm_client"]
