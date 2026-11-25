from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import AfterValidator, Field, StrictBool, model_validator

from support_copilot.application.ticket_rules import (
    SEVERITY_BY_LABEL,
    STATUS_BY_LABEL,
    parse_case_id,
)
from support_copilot.infrastructure.postgres.tickets import UNSET
from support_copilot.interface.api.deps import (
    AgentUser,
    CustomerUser,
    SignedIn,
    Tickets,
)
from support_copilot.interface.api.types import ApiModel, text

router = APIRouter()

Status = Literal[
    "Draft", "Submitted", "In progress", "Waiting for customer", "Resolved"
]
Severity = Literal["Low", "Normal", "High", "Critical"]


def _http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must be http or https")
    return value


def _must_be_true(value: bool) -> bool:
    if value is not True:
        raise ValueError("consent must be true")
    return value


class NewSource(ApiModel):
    id: text(200) | None = None
    title: text(500, 1)
    url: Annotated[text(2000), AfterValidator(_http_url)] | None = None


class NewTicket(ApiModel):
    title: text(2000, 1)
    category: text(200, 1)
    severity: Severity
    description: text(20000) = ""
    sources: list[NewSource] = Field(default_factory=list, max_length=50)
    ai_answer: text(20000) | None = None
    consent: Annotated[StrictBool, AfterValidator(_must_be_true)]


class Reply(ApiModel):
    body: text(20000, 1)
    status: Status | None = None


class TicketPatch(ApiModel):
    status: Status | None = None
    assignee: text(200) | None = None
    severity: Severity | None = None

    @model_validator(mode="after")
    def _something_to_change(self):
        sent = self.model_fields_set
        if not sent:
            raise ValueError("Send at least one field.")
        if any(f in sent and getattr(self, f) is None for f in ("status", "severity")):
            raise ValueError("status and severity cannot be null.")
        return self


class Comment(ApiModel):
    """Output models carry no input limits: stored rows may exceed them."""

    author: str
    role: str
    at: datetime
    body: str


class Source(ApiModel):
    id: str | None = None
    title: str
    url: str | None = None


class Ticket(ApiModel):
    id: str
    title: str
    category: str
    status: str
    severity: str
    created: datetime
    updated: datetime
    summary: str
    description: str
    reporter: str
    company: str
    plan: str
    sources: list[Source]
    ai_answer: str | None = None
    assignee: str | None = None
    comments: list[Comment]


@router.get("/tickets", response_model_exclude_none=True)
def list_tickets(user: SignedIn, tickets: Tickets) -> list[Ticket]:
    return [Ticket(**t) for t in tickets.list(user)]


@router.post("/tickets", status_code=201, response_model_exclude_none=True)
def create_ticket(body: NewTicket, user: CustomerUser, tickets: Tickets) -> Ticket:
    return Ticket(
        **tickets.create(
            user,
            {
                "title": body.title,
                "category": body.category,
                "severity": SEVERITY_BY_LABEL[body.severity],
                "description": body.description,
                "ai_answer": body.ai_answer or None,
                "sources": [s.model_dump() for s in body.sources],
            },
        )
    )


@router.get("/tickets/{ticket_id}", response_model_exclude_none=True)
def get_ticket(ticket_id: str, user: SignedIn, tickets: Tickets) -> Ticket:
    return Ticket(**tickets.get(user, parse_case_id(ticket_id)))


@router.patch("/tickets/{ticket_id}", response_model_exclude_none=True)
def patch_ticket(
    ticket_id: str, body: TicketPatch, user: SignedIn, tickets: Tickets
) -> Ticket:
    return Ticket(
        **tickets.patch(
            user,
            parse_case_id(ticket_id),
            STATUS_BY_LABEL.get(body.status),
            SEVERITY_BY_LABEL.get(body.severity),
            body.assignee if "assignee" in body.model_fields_set else UNSET,
        )
    )


@router.post("/tickets/{ticket_id}/take", response_model_exclude_none=True)
def take_ticket(ticket_id: str, user: AgentUser, tickets: Tickets) -> Ticket:
    return Ticket(**tickets.take(user, parse_case_id(ticket_id)))


@router.post("/tickets/{ticket_id}/replies", response_model_exclude_none=True)
def reply_to_ticket(
    ticket_id: str, body: Reply, user: SignedIn, tickets: Tickets
) -> Ticket:
    return Ticket(
        **tickets.reply(
            user, parse_case_id(ticket_id), body.body, STATUS_BY_LABEL.get(body.status)
        )
    )
