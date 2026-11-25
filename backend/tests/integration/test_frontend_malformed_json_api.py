import json

import pytest
from fastapi.testclient import TestClient

from support_copilot.interface.api.main import app

H = {"X-Demo-User": "mina", "Content-Type": "application/json"}


def raw(
    name='"n"',
    phone='""',
    notify='{"replies":true,"status":true,"digest":false}',
    extra="",
):
    return (
        "{" + extra + f'"name":{name},"email":"m@x.test","company":"c",'
        f'"timezone":"UTC","phone":{phone},"notify":{notify}' + "}"
    ).encode("ascii")


@pytest.mark.parametrize(
    "content",
    [
        raw(name=r'"\ud800"'),
        raw(extra=r'"\ud800":1,'),
        raw(extra=r'"x":"\ud800",'),
        raw(phone="NaN"),
        raw(extra='"x":NaN,'),
        raw(extra='"x":-Infinity,'),
        raw(notify="Infinity"),
    ],
)
def test_malformed_json_values_are_422_without_echoing_input(api, content):
    client = TestClient(app, raise_server_exceptions=False)
    response = client.put("/profile", headers=H, content=content)
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] and all(
        set(e) == {"type", "loc", "msg"} for e in body["detail"]
    )
    response.content.decode("ascii")


def test_chat_rejects_nan_with_422():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/chat",
        content=b'{"question":NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "input" not in json.dumps(response.json())
