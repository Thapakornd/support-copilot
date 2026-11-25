"""Shared by the ticket API tests (rootdir/conftest-less import: same directory)."""

from uuid import uuid4

import psycopg

CUSTOMER = {"X-Demo-User": "customer"}
MINA = {"X-Demo-User": "mina"}
JORDAN = {"X-Demo-User": "jordan"}
ALEX = {"X-Demo-User": "alex"}
PRIYA = {"X-Demo-User": "priya"}
SAM = {"X-Demo-User": "sam"}
OUTSIDER = {"X-Demo-User": "outsider"}

NEW = {
    "title": "Cannot connect",
    "category": "connectivity",
    "severity": "High",
    "consent": True,
}


def run(db, query, params=()):
    with psycopg.connect(db) as conn:
        cur = conn.execute(query, params or None)
        return cur.fetchall() if cur.description else None


def make(api, headers=CUSTOMER, **over):
    response = api.post("/tickets", headers=headers, json={**NEW, **over})
    assert response.status_code == 201, response.text
    return response.json()


def number(ticket):
    return int(ticket["id"].removeprefix("SC-"))


def add_outsider(db, subject="outsider"):
    """A customer in a different account."""
    account, user = uuid4(), uuid4()
    run(db, "INSERT INTO accounts(id, name) VALUES (%s, 'Other Org')", (account,))
    run(
        db,
        """INSERT INTO users(id, auth_issuer, auth_subject, email, display_name, role)
           VALUES (%s, 'demo', %s, 'o@x.test', 'Olive Outsider', 'customer')""",
        (user, subject),
    )
    run(
        db,
        "INSERT INTO account_memberships(account_id, user_id, team_role) VALUES (%s,%s,'Owner')",
        (account, user),
    )
    return {"X-Demo-User": subject}


def add_article(db, document_id, *, active=True, staged=False):
    revision = uuid4()
    run(
        db,
        "INSERT INTO knowledge_documents(document_id, data, is_active) VALUES (%s,'{}',%s)",
        (document_id, active),
    )
    run(
        db,
        """INSERT INTO knowledge_document_revisions
           (id, document_id, revision_hash, content_hash, title, source_url, source_type,
            product, deployment, version_scope, category_id, topics, content_markdown,
            excerpt, source_payload, fetched_at)
           VALUES (%s,%s,'h','c','T','https://example.org/a','documentation','mongodb-atlas',
                   'atlas','current','connectivity','{}','body','x','{}', now())""",
        (revision, document_id),
    )
    if not staged:
        run(
            db,
            "UPDATE knowledge_documents SET current_revision_id=%s WHERE document_id=%s",
            (revision, document_id),
        )
