"""Best-effort redaction of secrets and personal data before text is sent to an LLM.

This is not a guarantee. Regex and key-name matching will miss formats it has
not seen. Use synthetic or approved logs only.
"""

import json
import re
from typing import Any

REDACTED = "[REDACTED]"

# Key names whose values are always redacted (matched case-insensitively,
# as a suffix so that e.g. "db_password" or "x-api-key" are covered).
SENSITIVE_KEY_PATTERN = (
    r"[\w.-]*(?:password|passwd|pwd|passphrase|secret|token|api[_-]?key|access[_-]?key"
    r"|private[_-]?key|credentials?|session[_-]?id|cookie)"
)
_SENSITIVE_KEY_RE = re.compile(rf"(?i)^{SENSITIVE_KEY_PATTERN}$")

# Quoted value ("..." or '...') or a bare value up to a delimiter.
_VALUE = r"(?P<value>\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^\s,;}&]+)"


def _replace_kv(match: re.Match[str]) -> str:
    value = match.group("value")
    if value[:1] in ("'", '"'):
        replacement = f"{value[0]}{REDACTED}{value[0]}"
    else:
        replacement = REDACTED
    return f"{match.group('prefix')}{replacement}"


REDACTION_PATTERNS: list[tuple[re.Pattern[str], Any]] = [
    # PEM private keys / certificates bodies
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?bearer\s+)([^\s,;\"']+)"),
        rf"\1{REDACTED}",
    ),
    (
        re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(basic\s+[^\s,;\"']+)"),
        rf"\1{REDACTED}",
    ),
    # key=value, key: value, "key": "value", 'key': 'value'
    (
        re.compile(
            rf"(?i)(?P<prefix>(?P<q>[\"']?)\b{SENSITIVE_KEY_PATTERN}(?P=q)\s*[:=]\s*)" + _VALUE
        ),
        _replace_kv,
    ),
    # credentials embedded in URLs: scheme://user:pass@host
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@"),
        rf"\1{REDACTED}@",
    ),
    (
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s]+", re.IGNORECASE),
        "[REDACTED_CONNECTION_STRING]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[REDACTED_IP]",
    ),
]


def redact_structure(value: Any) -> Any:
    """Recursively redact a parsed JSON structure (dict/list/str)."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if isinstance(key, str) and _SENSITIVE_KEY_RE.match(key) else redact_structure(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, str):
        return _redact_patterns(value)
    return value


def _redact_patterns(text: str) -> str:
    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_text(text: str | None) -> str:
    """Redact a log message or any free text.

    If the whole text is a JSON object/array it is parsed and redacted by key
    name first, then pattern-based redaction runs on the result.
    """
    if not text:
        return ""
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            pass
        else:
            return json.dumps(redact_structure(parsed), ensure_ascii=False)
    return _redact_patterns(text)
