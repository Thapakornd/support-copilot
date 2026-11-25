"""Tickets: reads use a fixed number of queries; writes lock the ticket row,
call a pure rule from `application.ticket_rules`, and commit ticket + entries together."""

from collections.abc import Callable
from uuid import UUID, uuid4

import psycopg

from support_copilot.application.errors import Forbidden, NotFound, Unprocessable
from support_copilot.application.ticket_rules import (
    CONSENT_VERSION,
    SEVERITY_LABELS,
    STATUS_LABELS,
    Assignee,
    Change,
    Event,
    TicketState,
    opened,
)
from support_copilot.application.ticket_rules import patch as patch_rule
from support_copilot.application.ticket_rules import reply as reply_rule
from support_copilot.application.ticket_rules import take as take_rule
from support_copilot.domain.entities import CurrentUser
from support_copilot.infrastructure.postgres.connection import Database

_SELECT = """SELECT t.id, t.case_number, t.title, t.category_id, t.status, t.severity,
       t.created_at, t.updated_at, left(t.description, 200) AS summary, t.description,
       rep.display_name AS reporter, a.name AS company, a.plan_code AS plan,
       t.ai_answer_snapshot, asg.display_name AS assignee
FROM tickets t
JOIN users rep ON rep.id = t.reporter_id
JOIN accounts a ON a.id = t.account_id
LEFT JOIN users asg ON asg.id = t.assignee_id"""
_ORDER = " ORDER BY t.updated_at DESC, t.case_number DESC"
UNSET = object()


def _load(conn, where: str = "", params=()) -> list[dict]:
    """Tickets plus their comments and sources in three statements, however many."""
    rows = conn.execute(f"{_SELECT} {where}{_ORDER}", params).fetchall()
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    comments: dict = {i: [] for i in ids}
    for e in conn.execute(
        """SELECT ticket_id, actor_name_snapshot AS author, actor_role AS role,
                  created_at AS at, body
           FROM ticket_entries WHERE ticket_id = ANY(%s::uuid[]) ORDER BY entry_number""",
        (ids,),
    ):
        comments[e.pop("ticket_id")].append(e)
    sources: dict = {i: [] for i in ids}
    for s in conn.execute(
        """SELECT s.ticket_id, d.document_id AS id, s.title_snapshot AS title,
                  s.url_snapshot AS url
           FROM ticket_sources s
           LEFT JOIN knowledge_documents d ON d.document_id = s.document_id
                AND d.is_active AND d.current_revision_id IS NOT NULL
           WHERE s.ticket_id = ANY(%s::uuid[]) ORDER BY s.ticket_id, s.position""",
        (ids,),
    ):
        sources[s.pop("ticket_id")].append(s)
    return [
        {
            "id": f"SC-{r['case_number']}",
            "title": r["title"],
            "category": r["category_id"],
            "status": STATUS_LABELS[r["status"]],
            "severity": SEVERITY_LABELS[r["severity"]],
            "created": r["created_at"],
            "updated": r["updated_at"],
            "summary": r["summary"],
            "description": r["description"],
            "reporter": r["reporter"],
            "company": r["company"],
            "plan": r["plan"],
            "sources": sources[r["id"]],
            "ai_answer": r["ai_answer_snapshot"],
            "assignee": r["assignee"],
            "comments": comments[r["id"]],
        }
        for r in rows
    ]


def _read_only(conn) -> None:
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ


class TicketRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, user: CurrentUser) -> list[dict]:
        if user.role == "customer" and user.account_id is None:
            raise Forbidden
        with self.db.transaction(read_only=True) as conn:
            _read_only(conn)
            if user.role == "agent":
                return _load(conn)
            return _load(conn, "WHERE t.account_id = %s", (user.account_id,))

    def get(self, user: CurrentUser, number: int | None) -> dict:
        if number is None or (user.role == "customer" and user.account_id is None):
            raise NotFound
        where, params = "WHERE t.case_number = %s", [number]
        if user.role == "customer":
            where, params = where + " AND t.account_id = %s", [*params, user.account_id]
        with self.db.transaction(read_only=True) as conn:
            _read_only(conn)
            found = _load(conn, where, params)
        if not found:
            raise NotFound
        return found[0]

    def create(self, user: CurrentUser, new: dict) -> dict:
        if user.account_id is None:
            raise Forbidden
        with self.db.transaction() as conn:
            member = conn.execute(
                """SELECT can_open_cases FROM account_memberships
                   WHERE account_id = %s AND user_id = %s AND is_active FOR SHARE""",
                (user.account_id, user.id),
            ).fetchone()
            if not member or not member["can_open_cases"]:
                raise Forbidden
            if not conn.execute(
                "SELECT 1 FROM categories WHERE id = %s", (new["category"],)
            ).fetchone():
                raise Unprocessable("Unknown category.")
            known = {
                r["document_id"]: r["current_revision_id"]
                for r in conn.execute(
                    """SELECT document_id, current_revision_id FROM knowledge_documents
                       WHERE document_id = ANY(%s::text[]) AND is_active
                         AND current_revision_id IS NOT NULL""",
                    ([s["id"] for s in new["sources"] if s["id"]],),
                )
            }
            ticket_id = uuid4()
            now = conn.execute("SELECT clock_timestamp() AS ts").fetchone()["ts"]
            conn.execute(
                """INSERT INTO tickets (id, account_id, reporter_id, category_id, title,
                       description, severity, ai_answer_snapshot, consent_at,
                       consent_version, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    ticket_id, user.account_id, user.id, new["category"], new["title"],
                    new["description"], new["severity"], new["ai_answer"], now,
                    CONSENT_VERSION, now, now,
                ),
            )  # fmt: skip
            _add_entries(conn, ticket_id, user, None, (opened(new["ai_answer"]),))
            for position, s in enumerate(new["sources"], 1):
                revision = known.get(s["id"])
                conn.execute(
                    """INSERT INTO ticket_sources (ticket_id, position, document_id,
                           revision_id, title_snapshot, url_snapshot)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (
                        ticket_id, position, s["id"] if revision else None, revision,
                        s["title"], s["url"],
                    ),
                )  # fmt: skip
            return _load(conn, "WHERE t.id = %s", (ticket_id,))[0]

    def take(self, user: CurrentUser, number: int | None) -> dict:
        return self._write(user, number, lambda conn, state: take_rule(state, user))

    def reply(
        self, user: CurrentUser, number: int | None, body: str, status: str | None
    ) -> dict:
        return self._write(
            user, number, lambda conn, state: reply_rule(state, user, body, status)
        )

    def patch(
        self,
        user: CurrentUser,
        number: int | None,
        status: str | None,
        severity: int | None,
        assignee=UNSET,
    ) -> dict:
        """`assignee`: omit = unchanged, None/"" = unassign, else a display name."""

        def decide(conn, state: TicketState) -> Change:
            who = None
            if assignee is not UNSET:
                who = Assignee(None, None)
                # Customers are refused by the rule before the name matters.
                if assignee and user.role == "agent":
                    who = _resolve_agent(conn, assignee)
            return patch_rule(state, user, status, severity, who)

        return self._write(user, number, decide)

    def _write(
        self,
        user: CurrentUser,
        number: int | None,
        decide: Callable[[psycopg.Connection, TicketState], Change],
    ) -> dict:
        if number is None or (user.role == "customer" and user.account_id is None):
            raise NotFound
        where, params = "case_number = %s", [number]
        if user.role == "customer":
            where, params = where + " AND account_id = %s", [*params, user.account_id]
        with self.db.transaction() as conn:
            row = conn.execute(
                f"""SELECT id, status, severity, assignee_id, reporter_id
                    FROM tickets WHERE {where} FOR UPDATE""",
                params,
            ).fetchone()
            if row is None:
                raise NotFound
            change = decide(
                conn,
                TicketState(
                    row["status"],
                    row["severity"],
                    row["assignee_id"],
                    row["reporter_id"],
                ),
            )
            if change.effective:
                conn.execute(
                    """UPDATE tickets SET status = %(status)s, severity = %(severity)s,
                           assignee_id = %(assignee)s,
                           resolved_at = CASE WHEN %(status)s = 'resolved'
                               THEN COALESCE(resolved_at, clock_timestamp()) END,
                           version = version + 1, updated_at = clock_timestamp()
                       WHERE id = %(id)s""",
                    {
                        "status": change.status,
                        "severity": change.severity,
                        "assignee": change.assignee_id,
                        "id": row["id"],
                    },
                )
                _add_entries(conn, row["id"], user, change.reply, change.events)
            return _load(conn, "WHERE t.id = %s", (row["id"],))[0]


def _resolve_agent(conn, name: str) -> Assignee:
    """Exactly one active agent with this display name, else 422 (never guess)."""
    found = conn.execute(
        "SELECT id, display_name FROM users WHERE role = 'agent' AND is_active"
        " AND display_name = %s LIMIT 2",
        (name,),
    ).fetchall()
    if len(found) != 1:
        raise Unprocessable("Assignee must name exactly one active agent.")
    return Assignee(found[0]["id"], found[0]["display_name"])


def _add_entries(
    conn,
    ticket_id: UUID,
    actor: CurrentUser,
    reply: str | None,
    events: tuple[Event, ...],
) -> None:
    """The reply (if any) first, then the events, so entry_number keeps that order."""
    sql = """INSERT INTO ticket_entries (id, ticket_id, actor_id, actor_name_snapshot,
                 actor_role, kind, body, event_type, created_at)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())"""
    if reply is not None:
        conn.execute(
            sql,
            (
                uuid4(),
                ticket_id,
                actor.id,
                actor.name,
                actor.role,
                "reply",
                reply,
                None,
            ),
        )
    for e in events:
        conn.execute(
            sql,
            (uuid4(), ticket_id, actor.id, "System", "system", "event", e.body, e.type),
        )
