import psycopg
import pytest

H = {"X-Demo-User": "mina"}
BODY = {
    "name": "Mina P.",
    "email": "mina.p@demo.test",
    "company": "Acme",
    "timezone": "Europe/Berlin",
    "phone": "+66 1",
    "notify": {"replies": False, "status": True, "digest": True},
}


def test_get_profile_defaults_for_a_user_without_preferences(api):
    response = api.get("/profile", headers=H)
    assert response.status_code == 200
    assert response.json() == {
        "name": "Mina Park",
        "email": "mina@demo.test",
        "company": "Demo Org",
        "timezone": "Asia/Bangkok",
        "phone": "",
        "notify": {"replies": True, "status": True, "digest": False},
    }


def test_put_profile_saves_returns_and_persists_preferences(api, db):
    with psycopg.connect(db) as conn:
        before = conn.execute(
            "SELECT updated_at FROM users WHERE auth_subject='mina'"
        ).fetchone()[0]
    saved = api.put("/profile", headers=H, json=BODY)
    assert saved.status_code == 200
    assert saved.json() == BODY
    assert api.get("/profile", headers=H).json() == BODY
    with psycopg.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT updated_at FROM users WHERE auth_subject='mina'"
            ).fetchone()[0]
            > before
        )
        assert (
            conn.execute("SELECT count(*) FROM notification_preferences").fetchone()[0]
            == 1
        )
    # A second save updates the same preference row.
    again = {**BODY, "notify": {"replies": True, "status": False, "digest": False}}
    assert api.put("/profile", headers=H, json=again).json() == again
    with psycopg.connect(db) as conn:
        assert (
            conn.execute("SELECT count(*) FROM notification_preferences").fetchone()[0]
            == 1
        )


def test_put_profile_trims_and_keeps_an_empty_company(api):
    body = {**BODY, "name": "  Mina  ", "company": "   ", "phone": " "}
    saved = api.put("/profile", headers=H, json=body).json()
    assert (saved["name"], saved["company"], saved["phone"]) == ("Mina", "", "")
    assert api.get("/me", headers=H).json()["company"] == ""


def test_put_profile_never_touches_role_membership_or_auth(api, db):
    snapshot = (
        "SELECT role, auth_issuer, auth_subject, is_active FROM users ORDER BY id"
    )
    members = "SELECT account_id, user_id, team_role, can_open_cases, is_active FROM account_memberships ORDER BY user_id"
    with psycopg.connect(db) as conn:
        users, memberships = (
            conn.execute(snapshot).fetchall(),
            conn.execute(members).fetchall(),
        )
    assert api.put("/profile", headers=H, json=BODY).status_code == 200
    forbidden = api.put("/profile", headers=H, json={**BODY, "role": "agent"})
    assert forbidden.status_code == 422
    with psycopg.connect(db) as conn:
        assert conn.execute(snapshot).fetchall() == users
        assert conn.execute(members).fetchall() == memberships


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 201},
        {"email": "no-at"},
        {"email": "a b@x.test"},
        {"email": "a@b@c"},
        {"email": "a@" + "x" * 320},
        {"company": "x" * 201},
        {"phone": "9" * 51},
        {"timezone": "Mars/Olympus"},
        {"timezone": ""},
        {"name": "a\x00b"},
        {"company": "a\x00b"},
        {"notify": {"replies": True, "status": True}},
        {"notify": {"replies": "yes", "status": True, "digest": False}},
        {"unknown": 1},
    ],
)
def test_invalid_profile_is_422_and_changes_nothing(api, db, change):
    response = api.put("/profile", headers=H, json={**BODY, **change})
    assert response.status_code == 422
    assert api.get("/profile", headers=H).json()["name"] == "Mina Park"


def test_missing_body_field_is_422(api):
    body = {k: v for k, v in BODY.items() if k != "phone"}
    assert api.put("/profile", headers=H, json=body).status_code == 422


def test_failed_preference_write_rolls_back_the_user_update(api, db):
    with psycopg.connect(db) as conn:
        conn.execute(
            """CREATE FUNCTION boom() RETURNS trigger LANGUAGE plpgsql AS
               $$ BEGIN RAISE EXCEPTION 'boom'; END $$"""
        )
        conn.execute(
            """CREATE TRIGGER boom BEFORE INSERT OR UPDATE ON notification_preferences
               FOR EACH ROW EXECUTE FUNCTION boom()"""
        )
    from fastapi.testclient import TestClient

    from support_copilot.interface.api.main import app

    response = TestClient(app, raise_server_exceptions=False).put(
        "/profile", headers=H, json=BODY
    )
    assert response.status_code == 500
    with psycopg.connect(db) as conn:
        assert conn.execute(
            "SELECT display_name, email FROM users WHERE auth_subject='mina'"
        ).fetchone() == ("Mina Park", "mina@demo.test")


def test_profile_requires_a_signed_in_user(api):
    assert api.get("/profile").status_code == 401
    assert api.put("/profile", json=BODY).status_code == 401


def test_agent_profile_roundtrips(api):
    alex = {"X-Demo-User": "alex"}
    got = api.get("/profile", headers=alex).json()
    assert got["company"] == "Support Copilot · Support engineering"
    assert api.put("/profile", headers=alex, json=got).json() == got


def test_get_profile_tolerates_stored_values_that_break_input_limits(api, db):
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE users SET email='no-at-sign', display_name=%s, phone=%s, company=NULL "
            "WHERE auth_subject='mina'",
            ("n" * 300, "9" * 80),
        )
        conn.execute("UPDATE accounts SET name=%s", ("a" * 400,))
    response = api.get("/profile", headers=H)
    assert response.status_code == 200
    body = response.json()
    assert (body["email"], len(body["name"]), len(body["company"])) == (
        "no-at-sign",
        300,
        400,
    )
    assert api.get("/me", headers=H).status_code == 200
