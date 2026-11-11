import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import get_settings

BODY = {"question": "status?", "minutes": 5, "max_logs": 1}


@pytest.fixture
def client(monkeypatch):
    class NoLogs:
        def __init__(self, settings):
            pass

        def search_logs(self, request, limit):
            return []

    monkeypatch.setattr(main, "ElasticsearchLogClient", NoLogs)
    get_settings.cache_clear()
    yield TestClient(main.app)
    get_settings.cache_clear()


def test_ask_rejects_missing_or_wrong_key(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "test-key-123")
    get_settings.cache_clear()
    assert client.post("/ask", json=BODY).status_code == 401
    assert client.post("/ask", json=BODY, headers={"X-API-Key": "wrong"}).status_code == 401


def test_ask_accepts_correct_key(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "test-key-123")
    get_settings.cache_clear()
    resp = client.post("/ask", json=BODY, headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200
    assert resp.json()["logs_used"] == 0


def test_ask_open_when_api_key_unset(monkeypatch, client):
    monkeypatch.delenv("API_KEY", raising=False)
    get_settings.cache_clear()
    assert client.post("/ask", json=BODY).status_code == 200


def test_health_never_requires_key(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "test-key-123")
    get_settings.cache_clear()
    assert client.get("/health").status_code == 200
