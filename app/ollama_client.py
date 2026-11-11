import json
import logging
from urllib import error, request

from app.config import Settings
from app.exceptions import LLMClientError

LOGGER = logging.getLogger(__name__)


class OllamaClient:
    """Calls an Ollama server using the /api/generate endpoint."""

    def __init__(self, settings: Settings):
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout_seconds

    def generate_answer(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self._base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            LOGGER.exception("Ollama request failed with HTTP error")
            raise LLMClientError(f"Failed to query Ollama: HTTP {exc.code} {detail}") from exc
        except Exception as exc:
            LOGGER.exception("Ollama request failed")
            raise LLMClientError(f"Failed to query Ollama: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMClientError("Ollama returned a non-JSON response") from exc

        text = parsed.get("response")
        if text:
            return text.strip()

        err = parsed.get("error")
        if err:
            raise LLMClientError(f"Ollama error: {err}")

        raise LLMClientError("Ollama returned an empty response")
