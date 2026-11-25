"""Pure ticket rules: who may do what, the resulting change, and its ordered events.

No database here. The repository locks the ticket row, calls one rule, persists.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from support_copilot.application.errors import Conflict, Forbidden
from support_copilot.domain.entities import CurrentUser

CONSENT_VERSION = "case-share-v1"
MAX_CASE_NUMBER = 2**63 - 1

STATUS_LABELS = {
    "draft": "Draft",
    "submitted": "Submitted",
    "in_progress": "In progress",
    "waiting_for_customer": "Waiting for customer",
    "resolved": "Resolved",
}
STATUS_BY_LABEL = {label: value for value, label in STATUS_LABELS.items()}
SEVERITY_LABELS = {1: "Low", 2: "Normal", 3: "High", 4: "Critical"}
SEVERITY_BY_LABEL = {label: value for value, label in SEVERITY_LABELS.items()}

_TAKEABLE = {"submitted", "in_progress", "waiting_for_customer"}
_CASE_ID = re.compile(r"SC-([1-9][0-9]{0,18})")


@dataclass(frozen=True)
class TicketState:
    status: str
    severity: int
    assignee_id: UUID | None
    reporter_id: UUID


@dataclass(frozen=True)
class Event:
    type: str
    body: str


@dataclass(frozen=True)
class Assignee:
    """A resolved assignee; id None means unassign."""

    id: UUID | None
    name: str | None


@dataclass(frozen=True)
class Change:
    status: str
    severity: int
    assignee_id: UUID | None
    reply: str | None = None
    events: tuple[Event, ...] = ()

    @property
    def effective(self) -> bool:
        return self.reply is not None or bool(self.events)


def parse_case_id(raw: str) -> int | None:
    """`SC-<n>` exactly (ASCII digits, no leading zero, fits bigint), else None."""
    match = _CASE_ID.fullmatch(raw)
    number = int(match[1]) if match else 0
    return number if 0 < number <= MAX_CASE_NUMBER else None


def opened(ai_answer: str | None) -> Event:
    if ai_answer:
        return Event("escalated", "Escalated after the AI suggestion did not help")
    return Event("opened", "Case opened")


def _status_event(status: str) -> Event:
    return Event("status_changed", f"Status changed to {STATUS_LABELS[status]}")


def _reporter_only(state: TicketState, actor: CurrentUser) -> None:
    if actor.role != "customer" or actor.id != state.reporter_id:
        raise Forbidden


def take(state: TicketState, actor: CurrentUser) -> Change:
    if actor.role != "agent":
        raise Forbidden
    if state.assignee_id is not None or state.status not in _TAKEABLE:
        raise Conflict
    return Change(
        "in_progress",
        state.severity,
        actor.id,
        events=(Event("taken", f"{actor.name} took the case"),),
    )


def reply(
    state: TicketState, actor: CurrentUser, body: str, status: str | None
) -> Change:
    if actor.role == "agent":
        new = status or state.status
        assignee = state.assignee_id or actor.id
    else:
        _reporter_only(state, actor)
        if status is not None:
            raise Forbidden
        new = (
            "in_progress"
            if state.status in ("waiting_for_customer", "resolved")
            else state.status
        )
        assignee = state.assignee_id
    events = (_status_event(new),) if new != state.status else ()
    return Change(new, state.severity, assignee, reply=body, events=events)


def patch(
    state: TicketState,
    actor: CurrentUser,
    status: str | None,
    severity: int | None,
    assignee: Assignee | None,
) -> Change:
    """`assignee` None means the field was not sent; Assignee(None, None) unassigns."""
    if actor.role == "agent":
        return _agent_patch(state, status, severity, assignee)
    _reporter_only(state, actor)
    if severity is not None or assignee is not None:
        raise Forbidden
    if status not in (None, "resolved", "submitted"):
        raise Forbidden
    if status is None or status == state.status:
        return Change(state.status, state.severity, state.assignee_id)
    if status == "submitted" and state.status != "resolved":
        raise Conflict
    event = (
        Event("customer_resolved", "Customer marked the case resolved")
        if status == "resolved"
        else Event("customer_reopened", "Customer reopened the case")
    )
    return Change(status, state.severity, state.assignee_id, events=(event,))


def _agent_patch(state, status, severity, assignee) -> Change:
    events = []
    new_status = status or state.status
    if new_status != state.status:
        events.append(_status_event(new_status))
    new_assignee = state.assignee_id if assignee is None else assignee.id
    if new_assignee != state.assignee_id:
        events.append(
            Event("assigned", f"Assigned to {assignee.name}")
            if new_assignee
            else Event("unassigned", "Unassigned")
        )
    new_severity = severity or state.severity
    if new_severity != state.severity:
        events.append(
            Event(
                "severity_changed",
                f"Severity changed to {SEVERITY_LABELS[new_severity]}",
            )
        )
    return Change(new_status, new_severity, new_assignee, events=tuple(events))
