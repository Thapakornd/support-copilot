"""take / reply / PATCH over HTTP on a real PostgreSQL."""

import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ticket_helpers import (
    ALEX,
    CUSTOMER,
    JORDAN,
    MINA,
    PRIYA,
    SAM,
    add_outsider,
    make,
    number,
    run,
)


def url(t, suffix=""):
    return f"/tickets/{t['id']}{suffix}"


def stored(db, t):
    """Raw ticket row facts that the wire format hides."""
    version, status, resolved, updated, assignee = run(
        db,
        """SELECT t.version, t.status, t.resolved_at, t.updated_at, u.display_name
           FROM tickets t LEFT JOIN users u ON u.id = t.assignee_id
           WHERE t.case_number = %s""",
        (number(t),),
    )[0]
    return {"version": version, "status": status, "resolved_at": resolved,
            "updated_at": updated, "assignee": assignee}  # fmt: skip


def set_status(db, t, status):
    run(
        db,
        """UPDATE tickets SET status=%s,
               resolved_at = CASE WHEN %s='resolved' THEN now() END
           WHERE case_number=%s""",
        (status, status, number(t)),
    )


def events(ticket):
    return [c["body"] for c in ticket["comments"]]


def take(api, t, who=ALEX):
    response = api.post(url(t, "/take"), headers=who)
    assert response.status_code == 200, response.text
    return response.json()


def add_agent(db, subject, name, active=True, role="agent"):
    run(
        db,
        """INSERT INTO users(id, auth_issuer, auth_subject, email, display_name, role, is_active)
           VALUES (%s,'demo',%s,%s,%s,%s,%s)""",
        (uuid4(), subject, subject + "@x.test", name, role, active),
    )


# ---- take --------------------------------------------------------------
def test_take_assigns_sets_in_progress_and_logs_one_event(api, db):
    t = make(api)
    taken = api.post(url(t, "/take"), headers=ALEX)
    assert taken.status_code == 200
    body = taken.json()
    assert (body["assignee"], body["status"]) == ("Alex Chen", "In progress")
    assert events(body) == ["Case opened", "Alex Chen took the case"]
    assert (
        body["comments"][1]["author"] == "System"
        and body["comments"][1]["role"] == "system"
    )
    assert stored(db, t)["version"] == 2
    row = run(
        db,
        "SELECT actor_id IS NOT NULL, kind, event_type FROM ticket_entries "
        "ORDER BY entry_number DESC LIMIT 1",
    )[0]
    assert row == (True, "event", "taken")


@pytest.mark.parametrize("status", ["submitted", "in_progress", "waiting_for_customer"])
def test_take_allowed_from_open_states(api, db, status):
    t = make(api)
    set_status(db, t, status)
    assert api.post(url(t, "/take"), headers=ALEX).status_code == 200


def test_take_conflicts_do_not_change_anything(api, db):
    t = make(api)
    take(api, t)
    before = stored(db, t)
    assert api.post(url(t, "/take"), headers=PRIYA).status_code == 409
    assert api.post(url(t, "/take"), headers=ALEX).status_code == 409
    assert stored(db, t) == before
    for status in ("resolved", "draft"):
        other = make(api)
        set_status(db, other, status)
        assert api.post(url(other, "/take"), headers=ALEX).status_code == 409


def test_take_check_order(api, db):
    assert api.post("/tickets/SC-999999/take", headers=CUSTOMER).status_code == 403
    assert api.post("/tickets/SC-999999/take", headers=ALEX).status_code == 404
    t = make(api)
    assert api.post(url(t, "/take"), headers=CUSTOMER).status_code == 403
    assert stored(db, t)["assignee"] is None


def test_two_real_concurrent_takes_one_winner(api, db):
    for _ in range(5):
        t = make(api)
        barrier = threading.Barrier(2)
        out = {}

        def go(name, who):
            barrier.wait()
            out[name] = api.post(url(t, "/take"), headers=who)

        threads = [
            threading.Thread(target=go, args=("Alex Chen", ALEX)),
            threading.Thread(target=go, args=("Priya Nair", PRIYA)),
        ]
        [x.start() for x in threads]
        [x.join() for x in threads]
        codes = sorted(r.status_code for r in out.values())
        assert codes == [200, 409]
        winner = next(n for n, r in out.items() if r.status_code == 200)
        final = api.get(url(t), headers=ALEX).json()
        assert final["assignee"] == winner
        assert events(final).count(f"{winner} took the case") == 1
        assert sum(b.endswith("took the case") for b in events(final)) == 1
        assert stored(db, t)["version"] == 2


# ---- replies -----------------------------------------------------------
def reply(api, t, who, body="hello", **extra):
    return api.post(url(t, "/replies"), headers=who, json={"body": body, **extra})


def test_agent_reply_on_unassigned_assigns_without_extra_event(api, db):
    t = make(api)
    response = reply(api, t, ALEX, "  on it  ")
    assert response.status_code == 200
    body = response.json()
    assert (body["assignee"], body["status"]) == ("Alex Chen", "Submitted")
    assert [(c["author"], c["role"], c["body"]) for c in body["comments"]] == [
        ("System", "system", "Case opened"),
        ("Alex Chen", "agent", "on it"),
    ]
    assert stored(db, t)["version"] == 2


def test_agent_reply_with_status_puts_the_reply_before_the_event(api, db):
    t = make(api)
    body = reply(api, t, ALEX, "fixed", status="Resolved").json()
    assert events(body) == ["Case opened", "fixed", "Status changed to Resolved"]
    assert body["status"] == "Resolved"
    assert stored(db, t)["resolved_at"] is not None
    # no change of status: no event
    again = reply(api, t, ALEX, "still fixed", status="Resolved").json()
    assert events(again)[-1] == "still fixed"


def test_resolved_to_resolved_keeps_original_resolved_at(api, db):
    t = make(api)
    reply(api, t, ALEX, "done", status="Resolved")
    first = stored(db, t)["resolved_at"]
    reply(api, t, ALEX, "again", status="Resolved")
    assert stored(db, t)["resolved_at"] == first
    patched = api.patch(url(t), headers=ALEX, json={"severity": "Low"})
    assert patched.status_code == 200 and stored(db, t)["resolved_at"] == first


def test_reply_author_is_the_signed_in_agent_not_the_assignee(api):
    t = make(api)
    take(api, t, PRIYA)
    body = reply(api, t, ALEX, "from alex").json()
    assert body["assignee"] == "Priya Nair"
    assert body["comments"][-1]["author"] == "Alex Chen"


def test_customer_reply_hands_back_and_clears_resolved_at(api, db):
    waiting, resolved, submitted = make(api), make(api), make(api)
    set_status(db, waiting, "waiting_for_customer")
    reply(api, resolved, ALEX, "done", status="Resolved")
    w = reply(api, waiting, CUSTOMER, "more info").json()
    r = reply(api, resolved, CUSTOMER, "not fixed").json()
    s = reply(api, submitted, CUSTOMER, "ping").json()
    assert (w["status"], events(w)) == (
        "In progress",
        ["Case opened", "more info", "Status changed to In progress"],
    )
    assert (r["status"], events(r)[-2:]) == (
        "In progress",
        ["not fixed", "Status changed to In progress"],
    )
    assert stored(db, resolved)["resolved_at"] is None
    assert (s["status"], events(s)) == ("Submitted", ["Case opened", "ping"])
    assert w["comments"][1] | {"at": 0} == {
        "author": "Demo customer",
        "role": "customer",
        "body": "more info",
        "at": 0,
    }


def test_reply_permissions_and_validation(api, db):
    other = add_outsider(db)
    t = make(api)
    assert reply(api, t, CUSTOMER, "x", status="Resolved").status_code == 403
    for who in (MINA, JORDAN):
        assert reply(api, t, who, "x").status_code == 403
    assert reply(api, t, other, "x").status_code == 404
    assert reply(api, make(api, headers=other), CUSTOMER, "x").status_code == 404
    assert reply(api, {"id": "SC-999999"}, CUSTOMER, "x").status_code == 404
    assert reply(api, {"id": "SC-999999"}, ALEX, "x").status_code == 404
    for who in (CUSTOMER, ALEX):
        for body in ("", "   ", "x" * 20001, "a\x00b"):
            assert reply(api, t, who, body).status_code == 422
    assert reply(api, t, ALEX, "x", status="Nope").status_code == 422
    assert reply(api, t, ALEX, "x", severity="Low").status_code == 422
    assert reply(api, t, ALEX, "x" * 20000).status_code == 200
    assert stored(db, t)["version"] == 2


# ---- patch -------------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {}, {"status": None}, {"severity": None}, {"status": "Nope"},
        {"severity": 3}, {"x": 1}, {"assignee": "a\x00"}, {"assignee": "x" * 201},
        {"status": None, "assignee": "Alex Chen"},
    ],
)  # fmt: skip
def test_invalid_patch_bodies_are_422_for_agents_and_customers(api, db, body):
    t = make(api)
    for who in (ALEX, CUSTOMER):
        assert api.patch(url(t), headers=who, json=body).status_code == 422
    assert stored(db, t)["version"] == 1


def test_agent_patch_events_follow_the_fixed_order(api, db):
    t = make(api)
    body = api.patch(
        url(t), headers=ALEX,
        json={"severity": "Critical", "assignee": "Priya Nair", "status": "Waiting for customer"},
    ).json()  # fmt: skip
    assert events(body) == [
        "Case opened",
        "Status changed to Waiting for customer",
        "Assigned to Priya Nair",
        "Severity changed to Critical",
    ]
    assert (body["status"], body["severity"], body["assignee"]) == (
        "Waiting for customer",
        "Critical",
        "Priya Nair",
    )
    assert stored(db, t)["version"] == 2
    assert all(c["role"] == "system" for c in body["comments"])


@pytest.mark.parametrize("unassign", [None, "", "   "])
def test_assignee_null_or_blank_unassigns(api, db, unassign):
    t = make(api)
    take(api, t)
    body = api.patch(url(t), headers=ALEX, json={"assignee": unassign}).json()
    assert "assignee" not in body and events(body)[-1] == "Unassigned"
    assert stored(db, t)["assignee"] is None


def test_missing_assignee_is_unchanged_on_a_status_patch(api, db):
    t = make(api)
    take(api, t)
    body = api.patch(
        url(t), headers=ALEX, json={"status": "Waiting for customer"}
    ).json()
    assert body["assignee"] == "Alex Chen"
    assert events(body)[-1] == "Status changed to Waiting for customer"


def test_assignee_must_be_exactly_one_active_agent(api, db):
    add_agent(db, "alex2", "Alex Chen")  # ambiguous
    add_agent(db, "gone", "Gone Agent", active=False)
    t = make(api)
    for name in (
        "Nobody",
        "Gone Agent",
        "Mina Park",
        "Demo customer",
        "alex",
        "Alex Chen",
    ):
        r = api.patch(
            url(t), headers=SAM, json={"assignee": name, "status": "Resolved"}
        )
        assert r.status_code == 422, name
    assert stored(db, t)["version"] == 1 and stored(db, t)["status"] == "submitted"
    assert (
        api.patch(url(t), headers=SAM, json={"assignee": "Priya Nair"}).status_code
        == 200
    )


def test_noop_patches_change_nothing(api, db):
    t = make(api)
    take(api, t, PRIYA)
    before, snapshot = stored(db, t), api.get(url(t), headers=ALEX).json()
    for body in (
        {"status": "In progress"}, {"severity": "High"}, {"assignee": "Priya Nair"},
        {"status": "In progress", "severity": "High", "assignee": "Priya Nair"},
    ):  # fmt: skip
        r = api.patch(url(t), headers=ALEX, json=body)
        assert r.status_code == 200 and r.json() == snapshot
    assert stored(db, t) == before
    plain = make(api)
    assert api.patch(url(plain), headers=ALEX, json={"assignee": None}).json() == \
        api.get(url(plain), headers=ALEX).json()  # fmt: skip
    assert stored(db, plain)["version"] == 1


def test_assigning_the_current_assignee_while_the_name_is_ambiguous_is_422(api, db):
    # Chosen: ambiguity is never guessed, even when one of the matches is the current assignee.
    t = make(api)
    take(api, t, ALEX)
    add_agent(db, "alex2", "Alex Chen")
    assert (
        api.patch(url(t), headers=ALEX, json={"assignee": "Alex Chen"}).status_code
        == 422
    )
    assert api.patch(url(t), headers=ALEX, json={"severity": "Low"}).status_code == 200


def test_customer_resolves_and_reopens(api, db):
    t = make(api)
    take(api, t)
    done = api.patch(url(t), headers=CUSTOMER, json={"status": "Resolved"}).json()
    assert done["status"] == "Resolved"
    assert events(done)[-1] == "Customer marked the case resolved"
    assert stored(db, t)["resolved_at"] is not None
    first = stored(db, t)
    assert (
        api.patch(url(t), headers=CUSTOMER, json={"status": "Resolved"}).status_code
        == 200
    )
    assert stored(db, t) == first
    back = api.patch(url(t), headers=CUSTOMER, json={"status": "Submitted"}).json()
    assert back["status"] == "Submitted" and back["assignee"] == "Alex Chen"
    assert events(back)[-1] == "Customer reopened the case"
    assert stored(db, t)["resolved_at"] is None


def test_customer_reopen_only_from_resolved(api, db):
    t = make(api)
    assert (
        api.patch(url(t), headers=CUSTOMER, json={"status": "Submitted"}).status_code
        == 200
    )
    assert stored(db, t)["version"] == 1
    set_status(db, t, "in_progress")
    assert (
        api.patch(url(t), headers=CUSTOMER, json={"status": "Submitted"}).status_code
        == 409
    )
    assert stored(db, t)["version"] == 1


@pytest.mark.parametrize(
    "body",
    [
        {"status": "Draft"}, {"status": "In progress"}, {"status": "Waiting for customer"},
        {"severity": "Low"}, {"severity": "Normal"}, {"assignee": "Alex Chen"},
        {"assignee": None}, {"assignee": ""}, {"assignee": "Nobody At All"},
        {"status": "Resolved", "severity": "High"},
    ],
)  # fmt: skip
def test_customer_may_only_resolve_or_reopen(api, db, body):
    t = make(api)
    assert api.patch(url(t), headers=CUSTOMER, json=body).status_code == 403
    assert stored(db, t)["version"] == 1


def test_patch_check_order_and_scope(api, db):
    other = add_outsider(db)
    t = make(api)
    for who in (MINA, JORDAN):
        assert (
            api.patch(url(t), headers=who, json={"severity": "Low"}).status_code == 403
        )
        assert (
            api.patch(url(t), headers=who, json={"status": "Resolved"}).status_code
            == 403
        )
    assert api.patch(url(t), headers=other, json={"severity": "Low"}).status_code == 404
    assert (
        api.patch(url(t), headers=other, json={"status": "Resolved"}).status_code == 404
    )
    missing = "/tickets/SC-999999"
    assert (
        api.patch(missing, headers=CUSTOMER, json={"severity": "Low"}).status_code
        == 404
    )
    assert (
        api.patch(missing, headers=ALEX, json={"assignee": "Nobody"}).status_code == 404
    )
    assert stored(db, t)["version"] == 1


def test_effective_writes_bump_version_and_updated_at(api, db):
    t = make(api)
    before = stored(db, t)
    api.patch(url(t), headers=ALEX, json={"severity": "Low"})
    after = stored(db, t)
    assert after["version"] == before["version"] + 1
    assert after["updated_at"] > before["updated_at"]
    listed = api.get("/tickets", headers=ALEX).json()
    assert listed[0]["id"] == t["id"]


def test_concurrent_reply_and_patch_lose_no_update(api, db):
    t = make(api)
    barrier = threading.Barrier(2)
    out = []

    def post_reply():
        barrier.wait()
        out.append(reply(api, t, ALEX, "r", status="Waiting for customer"))

    def do_patch():
        barrier.wait()
        out.append(api.patch(url(t), headers=PRIYA, json={"severity": "Critical"}))

    threads = [threading.Thread(target=post_reply), threading.Thread(target=do_patch)]
    [x.start() for x in threads]
    [x.join() for x in threads]
    assert [r.status_code for r in out] == [200, 200]
    final = api.get(url(t), headers=ALEX).json()
    assert stored(db, t)["version"] == 3
    assert (final["status"], final["severity"]) == ("Waiting for customer", "Critical")
    assert "r" in events(final) and "Severity changed to Critical" in events(final)
    assert "Status changed to Waiting for customer" in events(final)


# ---- rollback ----------------------------------------------------------
TRIGGER = """
CREATE FUNCTION boom() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'boom'; END $$;
CREATE TRIGGER boom_trg BEFORE INSERT ON ticket_entries
FOR EACH ROW WHEN ({when}) EXECUTE FUNCTION boom();
"""


def test_failed_entry_insert_rolls_back_ticket_and_earlier_entries(api, db):
    from support_copilot.interface.api.main import app

    t = make(api)
    before = (stored(db, t), run(db, "SELECT count(*) FROM ticket_entries")[0][0])
    run(
        db,
        TRIGGER.format(when="NEW.kind = 'event' AND NEW.body LIKE 'Status changed%'"),
    )
    client = TestClient(app, raise_server_exceptions=False)
    # reply entry is inserted first, then the event insert fails
    r = client.post(
        url(t, "/replies"), headers=ALEX, json={"body": "x", "status": "Resolved"}
    )
    assert r.status_code == 500
    r = client.patch(
        url(t), headers=ALEX, json={"status": "Resolved", "severity": "Low"}
    )
    assert r.status_code == 500
    after = (stored(db, t), run(db, "SELECT count(*) FROM ticket_entries")[0][0])
    assert after == before


def test_failed_create_leaves_no_ticket_sources_or_entries(api, db):
    from support_copilot.interface.api.main import app

    run(db, TRIGGER.format(when="true"))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/tickets", headers=CUSTOMER,
        json={"title": "t", "category": "connectivity", "severity": "Low",
              "consent": True, "sources": [{"title": "s"}]},
    )  # fmt: skip
    assert r.status_code == 500
    counts = run(
        db,
        "SELECT (SELECT count(*) FROM tickets), (SELECT count(*) FROM ticket_entries),"
        " (SELECT count(*) FROM ticket_sources)",
    )[0]
    assert counts == (0, 0, 0)


@pytest.mark.parametrize(
    "method,suffix,raw",
    [
        ("patch", "", b'{"assignee":"\ud800"}'),
        ("patch", "", b'{"severity":NaN}'),
        ("post", "/replies", b'{"body":"\udfff"}'),
        ("post", "/replies", b'{"body":"x","status":NaN}'),
    ],
)
def test_lone_surrogate_and_nan_in_writes_are_422(api, method, suffix, raw):
    t = make(api)
    response = getattr(api, method)(
        url(t, suffix),
        headers={**ALEX, "Content-Type": "application/json"},
        content=raw,
    )
    assert response.status_code == 422
    response.content.decode("ascii")
