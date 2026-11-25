-- Optional and rerunnable; NOT part of the required 001..004 sequence.
-- Seeds the frontend's demo people for DEMO_AUTH=true (X-Demo-User: <subject>).
-- Existing rows are left untouched, so profile edits survive a rerun.
BEGIN;
SET LOCAL search_path = public;

INSERT INTO accounts (id, name, plan_code)
VALUES ('d0000000-0000-4000-8000-000000000001', 'Demo Org', 'developer')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, auth_issuer, auth_subject, email, display_name, role, company, timezone)
VALUES
    ('d0000000-0000-4000-8000-000000000011', 'demo', 'customer', 'customer@demo.test', 'Demo customer', 'customer', NULL, 'Asia/Bangkok'),
    ('d0000000-0000-4000-8000-000000000012', 'demo', 'mina', 'mina@demo.test', 'Mina Park', 'customer', NULL, 'Asia/Bangkok'),
    ('d0000000-0000-4000-8000-000000000013', 'demo', 'jordan', 'jordan@demo.test', 'Jordan Lee', 'customer', NULL, 'Asia/Bangkok'),
    ('d0000000-0000-4000-8000-000000000021', 'demo', 'alex', 'alex.chen@support.demo.test', 'Alex Chen', 'agent', U&'Support Copilot \00b7 Support engineering', 'Asia/Bangkok'),
    ('d0000000-0000-4000-8000-000000000022', 'demo', 'priya', 'priya.nair@support.demo.test', 'Priya Nair', 'agent', U&'Support Copilot \00b7 Support engineering', 'Asia/Bangkok'),
    ('d0000000-0000-4000-8000-000000000023', 'demo', 'sam', 'sam.okafor@support.demo.test', 'Sam Okafor', 'agent', U&'Support Copilot \00b7 Support engineering', 'Asia/Bangkok')
ON CONFLICT (auth_issuer, auth_subject) DO NOTHING;

-- Fixed offsets keep the team list in the frontend's order.
INSERT INTO account_memberships (account_id, user_id, team_role, can_open_cases, created_at)
SELECT 'd0000000-0000-4000-8000-000000000001', u.id, m.team_role, m.can_open_cases,
       timestamptz '2026-01-01 00:00:00+00' + m.n * interval '1 minute'
FROM (VALUES
    ('customer', 'Owner', true, 1),
    ('mina', 'Member', true, 2),
    ('jordan', 'Read only', false, 3)
) AS m (subject, team_role, can_open_cases, n)
JOIN users u ON u.auth_issuer = 'demo' AND u.auth_subject = m.subject
ON CONFLICT (account_id, user_id) DO NOTHING;
COMMIT;
