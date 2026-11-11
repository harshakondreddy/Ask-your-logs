from app.models import AskRequest, LogEntry
from app.redaction import redact_text

MAX_MESSAGE_CHARS = 120
MAX_QUESTION_CHARS = 500


def build_prompt(request: AskRequest, logs: list[LogEntry]) -> str:
    # Every user- or log-derived field is redacted here, not only the message,
    # so nothing reaches the LLM provider without passing through redaction.
    question = redact_text(request.question)[:MAX_QUESTION_CHARS]
    log_lines = "\n".join(
        f"{i+1}. [{redact_text(entry.component_log_level) or '?'}] "
        f"{redact_text(entry.component_name) or '?'}: "
        f"{redact_text(entry.message)[:MAX_MESSAGE_CHARS]}"
        for i, entry in enumerate(logs)
    )

    return f"""You are a log analysis assistant. Analyze these {len(logs)} log entries and answer: {question}

Respond in this EXACT format only:
Severity: High
Confidence: Medium
1. Overall status
<one sentence here>
2. Main issue
<one sentence here>
3. Business impact
<one sentence here>
4. Next best action
<one sentence here>

Rules: Use plain English. No commands. No extra text. Fill in each section.

Logs (last {request.minutes} mins):
{log_lines}

Your response:
"""
