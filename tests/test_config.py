from app.config import Settings


def test_tls_verification_on_by_default(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_VERIFY_CERTS", raising=False)
    assert Settings(_env_file=None).elasticsearch_verify_certs is True
