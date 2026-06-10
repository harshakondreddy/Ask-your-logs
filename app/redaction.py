import re


REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*)(basic\s+[^\s,;]+)"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|token|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?)\b\s*[:=]\s*['\"]?([^\s'\",;]+)['\"]?"
        ),
        r"\1=[REDACTED]",
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
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb|redis|amqp):\/\/[^\s]+", re.IGNORECASE),
        "[REDACTED_CONNECTION_STRING]",
    ),
]


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
