"""Ticket reads and creation over HTTP on a real PostgreSQL."""

from datetime import datetime
from urllib.parse import quote

import psycopg
import pytest
from ticket_helpers import (
    ALEX,
    CUSTOMER,
    JORDAN,
    MINA,
    NEW,
    add_article,
    add_outsider,
    make,
    run,
)

KEYS = {
    "id", "title", "category", "status", "severity", "created", "updated", "summary",
    "description", "reporter", "company", "plan", "sources", "comments",
}  # fmt: skip


# ---- 401 ---------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/tickets", None),
        ("post", "/tickets", NEW),
        ("get", "/tickets/SC-1", None),
        ("patch", "/tickets/SC-1", {"severity": "Low"}),
        ("post", "/tickets/SC-1/take", None),
        ("post", "/tickets/SC-1/replies", {"body": "x"}),
    ],
)
def test_every_ticket_endpoint_is_401_without_a_header(api, method, path, body):
    response = (
        getattr(api, method)(path, json=body) if body else getattr(api, method)(path)
    )
    assert response.status_code == 401


# ---- create ------------------------------------------------------------
def test_create_returns_the_spec_shape(api):
    response = api.post("/tickets", headers=CUSTOMER, json={**NEW, "description": "d"})
    assert response.status_code == 201
    t = response.json()
    assert set(t) == KEYS
    assert t["id"].startswith("SC-") and t["id"][3:].isdigit()
    assert (t["status"], t["severity"], t["category"]) == (
        "Submitted",
        "High",
        "connectivity",
    )
    assert (t["reporter"], t["company"], t["plan"]) == (
        "Demo customer",
        "Demo Org",
        "developer",
    )
    assert (t["summary"], t["description"], t["sources"]) == ("d", "d", [])
    assert [(c["author"], c["role"], c["body"]) for c in t["comments"]] == [
        ("System", "system", "Case opened")
    ]
    assert set(t["comments"][0]) == {"author", "role", "at", "body"}
    for value in (t["created"], t["updated"], t["comments"][0]["at"]):
        assert datetime.fromisoformat(value).utcoffset() is not None


def test_create_stores_consent_version_status_and_version(api, db):
    make(api)
    status, version, consent_at, cv, resolved = run(
        db,
        "SELECT status, version, consent_at, consent_version, resolved_at FROM tickets",
    )[0]
    assert (status, version, cv, resolved) == ("submitted", 1, "case-share-v1", None)
    assert consent_at is not None


def test_summary_is_first_200_chars_and_description_defaults_empty(api):
    long = "é" * 250
    t = make(api, description=long)
    assert t["summary"] == "é" * 200 and t["description"] == long
    plain = make(api)
    assert plain["description"] == "" and plain["summary"] == ""


def test_title_is_trimmed(api):
    assert make(api, title="  hi  ")["title"] == "hi"


def test_ai_answer_escalates_and_blank_is_absent(api):
    t = make(api, aiAnswer="Try this")
    assert t["aiAnswer"] == "Try this"
    assert t["comments"][0]["body"] == "Escalated after the AI suggestion did not help"
    blank = make(api, aiAnswer="   ")
    assert "aiAnswer" not in blank
    assert blank["comments"][0]["body"] == "Case opened"


@pytest.mark.parametrize("consent", ["missing", False, "true", 1, None])
def test_consent_must_be_true(api, consent):
    body = {k: v for k, v in NEW.items() if k != "consent"}
    if consent != "missing":
        body["consent"] = consent
    assert api.post("/tickets", headers=CUSTOMER, json=body).status_code == 422


@pytest.mark.parametrize(
    "over",
    [
        {"category": "nope"},
        {"category": ""},
        {"title": "   "},
        {"title": "x" * 2001},
        {"severity": "Urgent"},
        {"severity": 2},
        {"description": "x" * 20001},
        {"aiAnswer": "x" * 20001},
        {"status": "Resolved"},
        {"reporter": "someone"},
        {"sources": [{"title": ""}]},
        {"sources": [{"title": "x" * 501}]},
        {"sources": [{"title": "t", "url": "javascript:alert(1)"}]},
        {"sources": [{"title": "t", "url": "ftp://x.test/a"}]},
        {"sources": [{"title": "t", "url": "http://"}]},
        {"sources": [{"title": "t", "url": "https://x.test/" + "a" * 2000}]},
        {"sources": [{"title": "t"}] * 51},
        {"sources": [{"title": "t", "extra": 1}]},
        {"sources": None},
    ],
)
def test_create_rejects_invalid_input(api, over):
    response = api.post("/tickets", headers=CUSTOMER, json={**NEW, **over})
    assert response.status_code == 422


def test_create_accepts_limits(api):
    t = make(
        api, title="x" * 2000, sources=[{"title": "t"}] * 50, description="d" * 20000
    )
    assert len(t["sources"]) == 50


@pytest.mark.parametrize(
    "over",
    [
        {"title": "a\x00b"},
        {"description": "a\x00"},
        {"aiAnswer": "\x00"},
        {"category": "a\x00"},
        {"sources": [{"title": "a\x00"}]},
        {"sources": [{"title": "t", "url": "https://x.test/\x00"}]},
        {"sources": [{"title": "t", "id": "a\x00"}]},
    ],
)
def test_nul_anywhere_is_422(api, over):
    assert (
        api.post("/tickets", headers=CUSTOMER, json={**NEW, **over}).status_code == 422
    )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"title":"\\ud800","category":"connectivity","severity":"Low","consent":true}',
        b'{"title":"t","category":"connectivity","severity":NaN,"consent":true}',
        b'{"title":"t","category":"connectivity","severity":"Low","consent":true,"x":NaN}',
    ],
)
def test_lone_surrogate_and_nan_are_422(api, raw):
    response = api.post(
        "/tickets",
        headers={**CUSTOMER, "Content-Type": "application/json"},
        content=raw,
    )
    assert response.status_code == 422
    response.content.decode("ascii")


def test_create_roles_and_membership(api, db):
    assert api.post("/tickets", headers=ALEX, json=NEW).status_code == 403
    assert api.post("/tickets", headers=JORDAN, json=NEW).status_code == 403
    assert api.post("/tickets", headers=MINA, json=NEW).status_code == 201
    run(
        db,
        "UPDATE account_memberships SET is_active=false WHERE user_id IN "
        "(SELECT id FROM users WHERE auth_subject='customer')",
    )
    assert api.post("/tickets", headers=CUSTOMER, json=NEW).status_code == 403
    assert run(db, "SELECT count(*) FROM tickets")[0][0] == 1


def test_create_sources_keep_title_and_drop_unservable_ids(api, db):
    add_article(db, "good")
    add_article(db, "off", active=False)
    add_article(db, "staged", staged=True)
    sources = [
        {"id": "good", "title": "Good", "url": "https://x.test/g"},
        {"id": "off", "title": "Off"},
        {"id": "staged", "title": "Staged"},
        {"id": "nope", "title": "Nope", "url": "http://x.test/n"},
        {"title": "Plain"},
    ]
    t = make(api, sources=sources)
    assert t["sources"] == [
        {"id": "good", "title": "Good", "url": "https://x.test/g"},
        {"title": "Off"},
        {"title": "Staged"},
        {"title": "Nope", "url": "http://x.test/n"},
        {"title": "Plain"},
    ]
    run(db, "UPDATE knowledge_documents SET is_active=false WHERE document_id='good'")
    again = api.get(f"/tickets/{t['id']}", headers=CUSTOMER).json()
    assert again["sources"][0] == {"title": "Good", "url": "https://x.test/g"}
    assert (
        run(db, "SELECT count(*) FROM ticket_sources WHERE document_id IS NOT NULL")[0][
            0
        ]
        == 1
    )


# ---- read --------------------------------------------------------------
def test_list_scopes_by_account_and_orders_newest_updated_first(api, db):
    other = add_outsider(db)
    a, b, c = (
        make(api, title="a"),
        make(api, title="b"),
        make(api, headers=other, title="c"),
    )
    run(
        db,
        "UPDATE tickets SET updated_at = now() + interval '1 minute' WHERE title='a'",
    )
    mine = api.get("/tickets", headers=CUSTOMER).json()
    assert [t["id"] for t in mine] == [a["id"], b["id"]]
    assert [t["id"] for t in api.get("/tickets", headers=MINA).json()] == [
        a["id"],
        b["id"],
    ]
    assert [t["id"] for t in api.get("/tickets", headers=other).json()] == [c["id"]]
    every = [t["id"] for t in api.get("/tickets", headers=ALEX).json()]
    assert every == [a["id"], c["id"], b["id"]]


def test_list_without_active_membership_is_403(api, db):
    run(
        db,
        "UPDATE account_memberships SET is_active=false WHERE user_id IN "
        "(SELECT id FROM users WHERE auth_subject='customer')",
    )
    assert api.get("/tickets", headers=CUSTOMER).status_code == 403
    assert api.get("/tickets", headers=MINA).status_code == 200


def test_get_other_account_is_404_and_members_and_agents_can_read(api, db):
    other = add_outsider(db)
    t = make(api)
    url = f"/tickets/{t['id']}"
    assert api.get(url, headers=CUSTOMER).json() == t
    assert api.get(url, headers=MINA).status_code == 200
    assert api.get(url, headers=JORDAN).status_code == 200
    assert api.get(url, headers=ALEX).status_code == 200
    assert api.get(url, headers=other).status_code == 404
    assert api.get("/tickets/SC-999999", headers=ALEX).status_code == 404
    assert api.get("/tickets/SC-999999", headers=CUSTOMER).status_code == 404


def test_membership_deactivated_after_filing_loses_access(api, db):
    t = make(api)
    run(
        db,
        "UPDATE account_memberships SET is_active=false WHERE user_id IN "
        "(SELECT id FROM users WHERE auth_subject='customer')",
    )
    assert api.get(f"/tickets/{t['id']}", headers=CUSTOMER).status_code == 404
    assert api.get("/tickets", headers=CUSTOMER).status_code == 403
    r = api.post(f"/tickets/{t['id']}/replies", headers=CUSTOMER, json={"body": "hi"})
    assert r.status_code == 404
    r = api.patch(f"/tickets/{t['id']}", headers=CUSTOMER, json={"status": "Resolved"})
    assert r.status_code == 404


BAD_IDS = [
    "SC-abc", "SC-0", "SC--1", "SC-99999999999999999999", "sc-1", "SC-١",
    "SC-01", "%00", "SC-%00", "SC-9223372036854775808", "1", "SC-1%0A", "SC-+1",
]  # fmt: skip


@pytest.mark.parametrize("bad", BAD_IDS)
def test_malformed_ids_are_404_never_500(api, bad):
    path = "/tickets/" + (bad if "%" in bad else quote(bad))
    cases = [
        ("get", {}, CUSTOMER), ("get", {}, ALEX),
        ("patch", {"json": {"severity": "Low"}}, ALEX),
        ("patch", {"json": {"status": "Resolved"}}, CUSTOMER),
    ]  # fmt: skip
    for method, kwargs, who in cases:
        response = getattr(api, method)(path, headers=who, **kwargs)
        assert response.status_code == 404, (method, who, response.text)
    for who in (ALEX, CUSTOMER):
        response = api.post(path + "/replies", headers=who, json={"body": "x"})
        assert response.status_code == 404
    assert api.post(path + "/take", headers=ALEX).status_code == 404
    assert api.post(path + "/take", headers=CUSTOMER).status_code == 403


def test_list_uses_a_fixed_number_of_queries(api, monkeypatch):
    calls = []
    original = psycopg.Cursor.execute

    def counting(self, query, *args, **kwargs):
        calls.append(query)
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", counting)

    def count(n):
        for _ in range(n):
            make(api, sources=[{"title": "s"}], aiAnswer="x")
        calls.clear()
        assert len(api.get("/tickets", headers=ALEX).json()) >= n
        listed = len(calls)
        calls.clear()
        assert api.get("/tickets", headers=CUSTOMER).status_code == 200
        return listed, len(calls)

    few = count(2)
    many = count(6)
    assert few == many and max(few) <= 5


def test_comments_are_ordered_by_entry_number(api, db):
    t = make(api)
    run(
        db,
        """INSERT INTO ticket_entries(id, ticket_id, actor_name_snapshot, actor_role, kind, body, created_at)
               SELECT gen_random_uuid(), id, 'System', 'system', 'event', 'second',
                      now() - interval '1 day' FROM tickets""",
    )
    bodies = [
        c["body"]
        for c in api.get(f"/tickets/{t['id']}", headers=ALEX).json()["comments"]
    ]
    assert bodies == ["Case opened", "second"]
