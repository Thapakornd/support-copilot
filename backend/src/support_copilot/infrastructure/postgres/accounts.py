from uuid import UUID

from support_copilot.application.errors import Unprocessable
from support_copilot.domain.entities import CurrentUser
from support_copilot.infrastructure.postgres.connection import Database

_USER = """SELECT u.id, u.display_name AS name, u.email, u.role,
       COALESCE(u.company, a.name, '') AS company, m.account_id
FROM users u
LEFT JOIN LATERAL (
    SELECT m.account_id FROM account_memberships m
    WHERE m.user_id = u.id AND m.is_active AND u.role = 'customer'
    ORDER BY m.created_at, m.account_id LIMIT 1) m ON true
LEFT JOIN accounts a ON a.id = m.account_id"""


class AccountRepository:
    def __init__(self, db: Database):
        self.db = db

    def find_demo_user(self, subject: str) -> CurrentUser | None:
        with self.db.transaction(read_only=True) as conn:
            row = conn.execute(
                _USER + " WHERE u.auth_issuer = 'demo' AND u.auth_subject = %s"
                " AND u.is_active",
                (subject,),
            ).fetchone()
        return CurrentUser(**row) if row else None

    def list_agents(self) -> list[str]:
        with self.db.transaction(read_only=True) as conn:
            rows = conn.execute(
                "SELECT display_name FROM users WHERE role = 'agent' AND is_active"
            ).fetchall()
        return sorted(row["display_name"] for row in rows)

    def list_team(self, account_id: UUID) -> list[dict]:
        with self.db.transaction(read_only=True) as conn:
            return conn.execute(
                """SELECT u.display_name AS name, u.email, m.team_role AS role,
                          m.can_open_cases AS cases
                   FROM account_memberships m JOIN users u ON u.id = m.user_id
                   WHERE m.account_id = %s AND m.is_active AND u.is_active
                   ORDER BY m.created_at, u.display_name, u.id""",
                (account_id,),
            ).fetchall()

    def get_profile(self, user: CurrentUser) -> dict:
        with self.db.transaction(read_only=True) as conn:
            row = conn.execute(
                """SELECT u.timezone, COALESCE(u.phone, '') AS phone,
                          COALESCE(p.replies, true) AS replies,
                          COALESCE(p.status_changes, true) AS status,
                          COALESCE(p.weekly_digest, false) AS digest
                   FROM users u LEFT JOIN notification_preferences p ON p.user_id = u.id
                   WHERE u.id = %s""",
                (user.id,),
            ).fetchone()
        return _profile(user.name, user.email, user.company, row)

    def save_profile(self, user_id: UUID, p: dict) -> dict:
        with self.db.transaction() as conn:
            if not conn.execute(
                "SELECT 1 FROM pg_timezone_names WHERE name = %s", (p["timezone"],)
            ).fetchone():
                raise Unprocessable("Unknown timezone.")
            u = conn.execute(
                """UPDATE users SET display_name = %(name)s, email = %(email)s,
                       company = %(company)s, phone = %(phone)s, timezone = %(timezone)s,
                       updated_at = now()
                   WHERE id = %(id)s
                   RETURNING display_name AS name, email, COALESCE(company, '') AS company,
                             timezone, COALESCE(phone, '') AS phone""",
                {**p, "id": user_id},
            ).fetchone()
            n = conn.execute(
                """INSERT INTO notification_preferences
                       (user_id, replies, status_changes, weekly_digest)
                   VALUES (%(id)s, %(replies)s, %(status)s, %(digest)s)
                   ON CONFLICT (user_id) DO UPDATE SET replies = EXCLUDED.replies,
                       status_changes = EXCLUDED.status_changes,
                       weekly_digest = EXCLUDED.weekly_digest, updated_at = now()
                   RETURNING replies, status_changes AS status, weekly_digest AS digest""",
                {**p, "id": user_id},
            ).fetchone()
        return _profile(u["name"], u["email"], u["company"], {**u, **n})


def _profile(name: str, email: str, company: str, row: dict) -> dict:
    return {
        "name": name,
        "email": email,
        "company": company,
        "timezone": row["timezone"],
        "phone": row["phone"],
        "notify": {k: row[k] for k in ("replies", "status", "digest")},
    }
