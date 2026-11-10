import json

import pytest

from app.redaction import REDACTED, redact_text

# All values below are synthetic test data.
FAKE = "s3cr3t-Value_123"


@pytest.mark.parametrize(
    "text",
    [
        f"password={FAKE}",
        f"db_password: {FAKE}",
        f'"password": "{FAKE}"',
        f"'api_key': '{FAKE}'",
        f'{{"user": "svc", "client_secret": "{FAKE}"}}',
        f'request failed {{"x-api-key":"{FAKE}","status":401}} retrying',
        f"Authorization: Bearer {FAKE}",
        f"Authorization: Basic {FAKE}",
        f'"Authorization": "Bearer {FAKE}"',
        f"https://svc:{FAKE}@example.internal/path",
        f"postgresql://app:{FAKE}@db:5432/app",
        f"token={FAKE}&next=1",
    ],
)
def test_secret_value_removed(text):
    out = redact_text(text)
    assert FAKE not in out


def test_json_message_is_redacted_recursively_and_stays_valid_json():
    msg = json.dumps({"level": "ERROR", "auth": {"accessToken": FAKE}, "items": [{"password": FAKE}]})
    out = redact_text(msg)
    parsed = json.loads(out)
    assert parsed["auth"]["accessToken"] == REDACTED
    assert parsed["items"][0]["password"] == REDACTED
    assert parsed["level"] == "ERROR"


def test_email_jwt_ip_redacted():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    out = redact_text(f"user jane.doe@example.com from 192.0.2.10 sent {jwt}")
    assert "jane.doe@example.com" not in out
    assert "192.0.2.10" not in out
    assert jwt not in out


def test_private_key_block_redacted():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIBfake\n-----END RSA PRIVATE KEY-----"
    assert "MIIBfake" not in redact_text(f"loaded key {pem}")


def test_plain_text_untouched():
    text = "Connection refused while calling orders service, retry 3/5"
    assert redact_text(text) == text


def test_empty_and_none():
    assert redact_text("") == ""
    assert redact_text(None) == ""
