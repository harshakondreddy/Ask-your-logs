from app.models import AskRequest, LogEntry


def build_prompt(request: AskRequest, logs: list[LogEntry]) -> str:
    log_lines = "\n".join(
        f"{i+1}. [{entry.component_log_level or '?'}] {entry.component_name or '?'}: {entry.message[:120] if entry.message else ''}" 
        for i, entry in enumerate(logs)
    )

    return f"""You are a WES log analysis assistant. Analyze these {len(logs)} log entries and answer: {request.question}

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
