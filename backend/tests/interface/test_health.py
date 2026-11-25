from fastapi.testclient import TestClient

from support_copilot.interface.api.main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
