from pathlib import Path

import psycopg

SQL = Path(__file__).resolve().parents[2] / "sql" / "demo_identities.sql"


def run(db):
    with psycopg.connect(db) as conn:
        conn.execute(SQL.read_text())


def test_demo_identities_run_twice_and_keep_profile_edits(db):
    run(db)
    run(db)
    with psycopg.connect(db) as conn:
        assert conn.execute(
            """SELECT auth_subject, display_name, role FROM users
               WHERE auth_issuer='demo' ORDER BY auth_subject"""
        ).fetchall() == [
            ("alex", "Alex Chen", "agent"),
            ("customer", "Demo customer", "customer"),
            ("jordan", "Jordan Lee", "customer"),
            ("mina", "Mina Park", "customer"),
            ("priya", "Priya Nair", "agent"),
            ("sam", "Sam Okafor", "agent"),
        ]
        assert conn.execute("SELECT name FROM accounts").fetchall() == [("Demo Org",)]
        assert conn.execute(
            """SELECT u.auth_subject, m.team_role, m.can_open_cases
               FROM account_memberships m JOIN users u ON u.id=m.user_id
               ORDER BY m.created_at"""
        ).fetchall() == [
            ("customer", "Owner", True),
            ("mina", "Member", True),
            ("jordan", "Read only", False),
        ]
        conn.execute(
            """UPDATE users SET display_name='Edited', phone='555', company='',
               timezone='UTC', email='e@x.test' WHERE auth_subject='mina'"""
        )
        conn.execute(
            "UPDATE account_memberships SET team_role='Admin' WHERE team_role='Member'"
        )
        conn.commit()
    run(db)
    with psycopg.connect(db) as conn:
        assert conn.execute(
            """SELECT display_name, phone, company, timezone, email FROM users
               WHERE auth_subject='mina'"""
        ).fetchone() == ("Edited", "555", "", "UTC", "e@x.test")
        assert conn.execute(
            "SELECT team_role FROM account_memberships WHERE team_role='Admin'"
        ).fetchall() == [("Admin",)]
