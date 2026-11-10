from app.models import AskRequest, LogEntry
from app.prompt_builder import build_prompt

FAKE = "s3cr3t-Value_123"


def test_prompt_redacts_question_component_and_message():
    request = AskRequest(question=f"why does password={FAKE} fail?", minutes=30)
    logs = [
        LogEntry(
            component_name=f"svc token={FAKE}",
            component_log_level="ERROR",
            message=f'{{"apiKey": "{FAKE}", "msg": "boom"}}',
        )
    ]
    prompt = build_prompt(request, logs)
    assert FAKE not in prompt
    assert "ERROR" in prompt


def test_prompt_has_no_vendor_specific_wording():
    prompt = build_prompt(AskRequest(question="status?"), [LogEntry(message="ok")])
    assert "WES" not in prompt
