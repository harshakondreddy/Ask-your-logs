import logging

from openai import AzureOpenAI, OpenAI

from app.config import Settings
from app.exceptions import LLMClientError

LOGGER = logging.getLogger(__name__)


class OpenAIClient:
    """Calls the OpenAI chat completions API."""

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise LLMClientError("OPENAI_API_KEY is not configured")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def generate_answer(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content
            if text:
                return text.strip()
            raise LLMClientError("OpenAI returned an empty response")
        except LLMClientError:
            raise
        except Exception as exc:
            LOGGER.exception("OpenAI request failed")
            raise LLMClientError(f"Failed to query OpenAI: {exc}") from exc


class AzureOpenAIClient:
    """Calls the Azure OpenAI chat completions API."""

    def __init__(self, settings: Settings):
        if not settings.azure_openai_api_key:
            raise LLMClientError("AZURE_OPENAI_API_KEY is not configured")
        if not settings.azure_openai_endpoint:
            raise LLMClientError("AZURE_OPENAI_ENDPOINT is not configured")
        if not settings.azure_openai_deployment:
            raise LLMClientError("AZURE_OPENAI_DEPLOYMENT is not configured")
        self._client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment

    def generate_answer(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content
            if text:
                return text.strip()
            raise LLMClientError("Azure OpenAI returned an empty response")
        except LLMClientError:
            raise
        except Exception as exc:
            LOGGER.exception("Azure OpenAI request failed")
            raise LLMClientError(f"Failed to query Azure OpenAI: {exc}") from exc
