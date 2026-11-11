import logging

from google import genai

from app.config import Settings
from app.exceptions import LLMClientError

LOGGER = logging.getLogger(__name__)


class GeminiClientError(LLMClientError):
    pass


class GeminiClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        if not settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate_answer(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_model,
                contents=prompt,
            )
        except Exception as exc:
            LOGGER.exception("Gemini request failed")
            raise GeminiClientError(f"Failed to query Gemini: {exc}") from exc

        text = getattr(response, "text", None)
        if text:
            return text.strip()
        raise GeminiClientError("Gemini returned an empty response")
