import psycopg
import pytest
from pydantic import SecretStr

from support_copilot.core.config import settings


def as_user(subject):
    return {"X-Demo-User": subject}


def test_me_for_customer_and_agent(api):
    customer = api.get("/me", headers=as_user("customer"))
    assert customer.status_code == 200
    assert customer.json() == {
        "name": "Demo customer",
        "email": "customer@demo.test",
        "company": "Demo Org",
        "role": "customer",
    }
    agent = api.get("/me", headers=as_user("alex")).json()
    assert agent["company"] == "Support Copilot · Support engineering"
    assert agent["role"] == "agent"


def test_demo_auth_off_is_401_even_with_a_valid_header(api, monkeypatch):
    monkeypatch.setattr(settings, "demo_auth", False)
    response = api.get("/me", headers=as_user("customer"))
    assert response.status_code == 401
    assert "detail" in response.json()


def test_demo_auth_off_is_401_before_database_is_consulted(api, monkeypatch):
    monkeypatch.setattr(settings, "demo_auth", False)
    monkeypatch.setattr(settings, "database_url", SecretStr(""))
    assert api.get("/me", headers=as_user("customer")).status_code == 401


@pytest.mark.parametrize("subject", [None, "", "   ", "nobody", "a\x00b"])
def test_missing_blank_unknown_or_nul_subject_is_401(api, subject):
    headers = {} if subject is None else as_user(subject)
    assert api.get("/me", headers=headers).status_code == 401


def test_inactive_user_is_401(api, db):
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE users SET is_active=false WHERE auth_subject='mina'")
    assert api.get("/me", headers=as_user("mina")).status_code == 401


def test_only_demo_issuer_identities_match(api, db):
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE users SET auth_issuer='other' WHERE auth_subject='mina'")
    assert api.get("/me", headers=as_user("mina")).status_code == 401


def test_company_falls_back_to_account_and_empty_string_stays_empty(api, db):
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE users SET company='' WHERE auth_subject='mina'")
        conn.execute("UPDATE users SET company='Acme' WHERE auth_subject='jordan'")
    assert api.get("/me", headers=as_user("mina")).json()["company"] == ""
    assert api.get("/me", headers=as_user("jordan")).json()["company"] == "Acme"


def test_customer_without_account_has_empty_company(api, db):
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE account_memberships SET is_active=false")
    assert api.get("/me", headers=as_user("customer")).json()["company"] == ""


def test_missing_database_url_and_unreachable_database_are_503(api, monkeypatch):
    monkeypatch.setattr(settings, "database_url", SecretStr(""))
    missing = api.get("/me", headers=as_user("customer"))
    assert missing.status_code == 503
    monkeypatch.setattr(
        settings,
        "database_url",
        SecretStr("postgresql://u:secretpw@127.0.0.1:1/none?connect_timeout=1"),
    )
    down = api.get("/me", headers=as_user("customer"))
    assert down.status_code == 503
    assert "secretpw" not in down.text and "127.0.0.1" not in down.text
    assert down.json() == missing.json()


def test_agents_are_sorted_active_names_and_agent_only(api, db):
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE users SET is_active=false WHERE auth_subject='sam'")
    ok = api.get("/agents", headers=as_user("alex"))
    assert ok.json() == ["Alex Chen", "Priya Nair"]
    assert api.get("/agents", headers=as_user("customer")).status_code == 403
    assert api.get("/agents").status_code == 401


def test_team_lists_active_members_in_membership_order_and_is_customer_only(api, db):
    team = api.get("/team", headers=as_user("mina")).json()
    assert team == [
        {
            "name": "Demo customer",
            "email": "customer@demo.test",
            "role": "Owner",
            "cases": True,
        },
        {
            "name": "Mina Park",
            "email": "mina@demo.test",
            "role": "Member",
            "cases": True,
        },
        {
            "name": "Jordan Lee",
            "email": "jordan@demo.test",
            "role": "Read only",
            "cases": False,
        },
    ]
    assert api.get("/team", headers=as_user("alex")).status_code == 403
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE account_memberships SET is_active=false WHERE team_role='Member'"
        )
        conn.execute("UPDATE users SET is_active=false WHERE auth_subject='jordan'")
    assert [
        m["name"] for m in api.get("/team", headers=as_user("customer")).json()
    ] == ["Demo customer"]


def test_team_for_customer_without_account_is_403(api, db):
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE account_memberships SET is_active=false")
    assert api.get("/team", headers=as_user("customer")).status_code == 403
