from uuid import uuid4

import pytest

from support_copilot.application.errors import Conflict, Forbidden
from support_copilot.application.ticket_rules import (
    Assignee,
    TicketState,
    opened,
    parse_case_id,
    patch,
    reply,
    take,
)
from support_copilot.domain.entities import CurrentUser

CUSTOMER = CurrentUser(uuid4(), "Cu Stomer", "c@x", "Org", "customer", uuid4())
OTHER = CurrentUser(uuid4(), "Mina", "m@x", "Org", "customer", CUSTOMER.account_id)
ALEX = CurrentUser(uuid4(), "Alex Chen", "a@x", "Co", "agent", None)
PRIYA = CurrentUser(uuid4(), "Priya Nair", "p@x", "Co", "agent", None)


def state(status="submitted", severity=2, assignee=None):
    return TicketState(status, severity, assignee, CUSTOMER.id)


def bodies(change):
    return [e.body for e in change.events]


# take
def test_take_assigns_sets_in_progress_and_logs_one_event():
    c = take(state(), ALEX)
    assert (c.status, c.assignee_id, c.reply) == ("in_progress", ALEX.id, None)
    assert bodies(c) == ["Alex Chen took the case"]


@pytest.mark.parametrize("status", ["submitted", "in_progress", "waiting_for_customer"])
def test_take_allowed_states(status):
    assert take(state(status), ALEX).assignee_id == ALEX.id


@pytest.mark.parametrize("status", ["draft", "resolved"])
def test_take_wrong_status_is_conflict(status):
    with pytest.raises(Conflict):
        take(state(status), ALEX)


def test_take_assigned_is_conflict_and_customer_is_forbidden():
    with pytest.raises(Conflict):
        take(state(assignee=PRIYA.id), ALEX)
    with pytest.raises(Forbidden):
        take(state(), CUSTOMER)


# reply
def test_agent_reply_unassigned_assigns_without_event_and_keeps_status():
    c = reply(state(), ALEX, "hi", None)
    assert (c.status, c.assignee_id, c.reply, c.events) == (
        "submitted",
        ALEX.id,
        "hi",
        (),
    )


def test_agent_reply_keeps_other_assignee():
    c = reply(state(assignee=PRIYA.id), ALEX, "hi", None)
    assert c.assignee_id == PRIYA.id


def test_agent_reply_with_status_adds_event_only_when_changed():
    c = reply(
        state("in_progress", assignee=ALEX.id), ALEX, "hi", "waiting_for_customer"
    )
    assert (c.status, bodies(c)) == (
        "waiting_for_customer",
        ["Status changed to Waiting for customer"],
    )
    same = reply(state("resolved", assignee=ALEX.id), ALEX, "hi", "resolved")
    assert same.events == () and same.reply == "hi"


@pytest.mark.parametrize("status", ["waiting_for_customer", "resolved"])
def test_customer_reply_hands_back_to_support(status):
    c = reply(state(status, assignee=ALEX.id), CUSTOMER, "hi", None)
    assert c.status == "in_progress"
    assert bodies(c) == ["Status changed to In progress"]
    assert c.assignee_id == ALEX.id


@pytest.mark.parametrize("status", ["submitted", "in_progress"])
def test_customer_reply_leaves_other_statuses(status):
    c = reply(state(status), CUSTOMER, "hi", None)
    assert (c.status, c.events, c.assignee_id) == (status, (), None)


def test_customer_reply_rules_403():
    with pytest.raises(Forbidden):
        reply(state(), CUSTOMER, "hi", "resolved")
    with pytest.raises(Forbidden):
        reply(state(), OTHER, "hi", None)


# patch
def test_agent_patch_events_in_fixed_order():
    s = state("submitted", 2, PRIYA.id)
    c = patch(s, ALEX, "resolved", 4, Assignee(ALEX.id, "Alex Chen"))
    assert bodies(c) == [
        "Status changed to Resolved",
        "Assigned to Alex Chen",
        "Severity changed to Critical",
    ]
    assert (c.status, c.severity, c.assignee_id) == ("resolved", 4, ALEX.id)


def test_agent_unassign_event_and_missing_assignee_unchanged():
    s = state(assignee=PRIYA.id)
    assert bodies(patch(s, ALEX, None, None, Assignee(None, None))) == ["Unassigned"]
    c = patch(s, ALEX, "in_progress", None, None)
    assert c.assignee_id == PRIYA.id


def test_patch_that_changes_nothing_is_not_effective():
    s = state("in_progress", 2, PRIYA.id)
    c = patch(s, ALEX, "in_progress", 2, Assignee(PRIYA.id, "Priya Nair"))
    assert not c.effective and c.events == ()
    assert not patch(state(), ALEX, None, None, Assignee(None, None)).effective


def test_customer_resolve_and_reopen():
    c = patch(state("in_progress"), CUSTOMER, "resolved", None, None)
    assert (c.status, bodies(c)) == ("resolved", ["Customer marked the case resolved"])
    r = patch(state("resolved"), CUSTOMER, "submitted", None, None)
    assert (r.status, bodies(r)) == ("submitted", ["Customer reopened the case"])


def test_customer_noop_and_conflicts():
    assert not patch(state("resolved"), CUSTOMER, "resolved", None, None).effective
    assert not patch(state("submitted"), CUSTOMER, "submitted", None, None).effective
    with pytest.raises(Conflict):
        patch(state("in_progress"), CUSTOMER, "submitted", None, None)


@pytest.mark.parametrize("status", ["draft", "in_progress", "waiting_for_customer"])
def test_customer_other_statuses_forbidden(status):
    with pytest.raises(Forbidden):
        patch(state("resolved"), CUSTOMER, status, None, None)


def test_customer_assignee_or_severity_forbidden_even_if_unchanged():
    with pytest.raises(Forbidden):
        patch(state(), CUSTOMER, None, 2, None)
    with pytest.raises(Forbidden):
        patch(state(), CUSTOMER, None, None, Assignee(None, None))
    with pytest.raises(Forbidden):
        patch(state(), OTHER, "resolved", None, None)


# create / ids
def test_opened_event_depends_on_ai_answer():
    assert opened("x").body == "Escalated after the AI suggestion did not help"
    assert opened(None).body == "Case opened"


@pytest.mark.parametrize(
    "raw,expected",
    [("SC-1", 1), ("SC-10482", 10482), ("SC-9223372036854775807", 9223372036854775807)],
)
def test_parse_case_id_valid(raw, expected):
    assert parse_case_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "SC-abc",
        "SC-0",
        "SC--1",
        "SC-99999999999999999999",
        "sc-1",
        "SC-١",
        "SC-01",
        "SC-9223372036854775808",
        "SC-1\n",
        "SC-1 ",
        " SC-1",
        "SC-",
        "1",
        "",
        "SC-\x00",
        "SC-+1",
        "SC-1.0",
    ],
)
def test_parse_case_id_invalid(raw):
    assert parse_case_id(raw) is None
