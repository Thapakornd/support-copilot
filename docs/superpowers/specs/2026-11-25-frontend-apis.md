# Missing frontend APIs

Build the 14 endpoints that `frontend/src/shared/api/` still fakes in the browser. Product rules come from
[pages-and-features](../../frontend/pages-and-features.md); storage comes from
[the schema design](2026-11-14-database-schema-design.md) and `backend/sql/`, which already has every table needed.
**No schema migration.** Where those two documents disagree, this spec decides (see Decisions).

## What is missing

| Endpoint | Frontend function | Role |
|---|---|---|
| `GET /me` | `getMe` | both |
| `GET /agents` | `listAgents` | agent |
| `GET /profile`, `PUT /profile` | `getProfile`, `saveProfile` | both |
| `GET /team` | `listTeam` | customer |
| `GET /articles` | `listArticles` | both |
| `GET /articles/search?q=&topic=` | `searchArticles` | both |
| `GET /articles/{id}` | `getArticle` | both |
| `GET /tickets`, `POST /tickets` | `listTickets`, `createTicket` | both / customer |
| `GET /tickets/{id}`, `PATCH /tickets/{id}` | `getTicket`, `updateTicket` | both |
| `POST /tickets/{id}/take` | `takeTicket` | agent |
| `POST /tickets/{id}/replies` | `replyToTicket` | both |

**Out of scope:** real login, feedback votes (answer votes first need `/chat` to persist `ai_interactions`),
pagination, frontend wiring, deleting the demo adapters.

## Decisions

1. **Identity.** There is no login yet. `X-Demo-User: <subject>` selects the user with
   `auth_issuer='demo' AND auth_subject=<subject>`. It works only when `DEMO_AUTH=true` (default **false**); when
   false every endpoint here returns 401. Settings validation rejects `DEMO_AUTH=true` unless `API_HOST` is
   `127.0.0.1`, `localhost` or `::1`, because the header is impersonation by design. One FastAPI dependency
   resolves the user, so real auth replaces one function.
2. **Assignee is an agent display name** on the wire, as the frontend sends today, resolved to exactly one active
   agent. Zero or several matches give 422; never guess. (The schema design prefers IDs; switch if names collide.)
3. **PATCH:** a missing field is unchanged; `assignee` of `null` or `""` unassigns. (pages-and-features says
   "missing = unassign", which would unassign on every status change.) An empty patch is 422.
4. **Reply author is always the signed-in user**, never the assignee (schema design overrides the demo).
5. **Write scope:** account members read all account tickets; only the reporter replies, resolves or reopens.
6. **Consent:** `POST /tickets` requires `consent: true`. Store `consent_at` and the server constant
   `CONSENT_VERSION = "case-share-v1"`.
7. **Agents list is agent-only.** The case sidebar asks for it as a customer too; gate that when wiring.
8. **Article `updated` is ISO 8601**, not display text. Article bodies are markdown in an added `content` field;
   `body` is present only when `display_body` holds `{steps, note?}`. Never derive steps from markdown.

## Conventions

- JSON is camelCase, matching the TypeScript types. Omit null optional fields (`response_model_exclude_none`).
- Timestamps are ISO 8601 with an offset.
- Labels map to storage: status `Draft|Submitted|In progress|Waiting for customer|Resolved` ↔
  `draft|submitted|in_progress|waiting_for_customer|resolved`; severity `Low|Normal|High|Critical` ↔ 1..4.
- Errors are `{"detail": ...}`: 401 no valid user, 403 role or ownership, 404 missing **or in another account**,
  409 state conflict, 422 invalid input, 503 database unreachable (no internal detail leaked).
  Check order: 401, then role 403, then 404, then ownership 403, then 409/422 on state. FastAPI's own body 422 may
  precede role checks.
- Every inbound string (body, query, path) rejects NUL (U+0000), which PostgreSQL cannot store: 422 in a body or
  query, 404 in a path ID, 401 in the demo header. Malformed or bigint-overflowing case IDs are 404. Nothing a
  client sends may cause a 500.
- Body models forbid unknown fields, except that `POST /tickets` etc. never read identity from the body.

## Identity and account

`CurrentUser`: id, name, email, company, role, and `account_id` (customers: earliest active membership by
`created_at, account_id`; one account per customer for now). Unknown, inactive or blank subject: 401.

- `GET /me` → `{name, email, company, role}`. `company` = `users.company`, else the account name, else `""`.
  An empty string saved by the user stays empty.
- `GET /agents` → names of active agents, sorted.
- `GET /profile` → `{name, email, company, timezone, phone, notify: {replies, status, digest}}`. Null phone is
  `""`. No preference row: defaults `true, true, false`.
- `PUT /profile` takes that full shape, returns the saved shape, and upserts preferences in the same transaction.
  Trim; name required (≤200); email must match `^[^@\s]+@[^@\s]+$` (≤320); company ≤200; phone ≤50; timezone must
  exist in `pg_timezone_names`, else 422. Never touches role, membership or auth fields. Bumps `updated_at`.
- `GET /team` → `{name, email, role, cases}[]` for active members of the caller's account: `role` = `team_role`,
  `cases` = `can_open_cases`; sorted by membership `created_at`, then name. Customer without an account: 403.

## Articles

Serve active documents joined to `current_revision_id` (staged or inactive documents are invisible). 404 otherwise.

`Article = {id, title, type, product, topic, updated, excerpt}`; `id` = `document_id`, `topic` = `category_id`,
`updated` = `fetched_at`. Map `source_type`: `documentation`→`Documentation`, `knowledge-article`→`Knowledge Article`,
`community-forum`→`Community Forum`, `video`→`Video`. Map `product`: `mongodb-atlas`→`Atlas`,
`mongodb-server`→`Server`, `mongodb-drivers`→`Drivers`, `mongodb-ops-manager`→`Ops Manager`. Already-mapped labels pass
through; any other value falls back to `Documentation` / `Server`.

Stored excerpts are raw markdown (`# Title\n\n...`). Return plain text: drop heading lines, turn `[text](url)` into
`text`, strip `**`, `__` and backticks, collapse whitespace.

- `GET /articles`: newest `updated` first, then id.
- `GET /articles/{id}`: Article plus `content` (markdown), `sourceUrl`, and optional `body`.
- `GET /articles/search`: `q` ≤4000 chars, optional `topic`. PostgreSQL full text, english config, matching **any** query
  word, because users type full sentences: OR the lexemes of `plainto_tsquery`. Return matches only, best first,
  title weighted above body, normalised for length (a 60k-char page must not win on length alone); ties by id; at most 50.
  Blank `q`, or `q` with no lexemes: blank returns the `GET /articles` order (within `topic`), stop-words-only returns `[]`.
  Unknown topic returns `[]`. `/articles/search` must not be captured by `/articles/{id}`.

## Tickets

`Ticket = {id, title, category, status, severity, created, updated, summary, description, reporter, company, plan,
sources, aiAnswer?, assignee?, comments}`. `id` = `SC-<case_number>`; `summary` = first 200 chars of description;
`reporter`/`assignee` are current display names; `company`/`plan` = account name/`plan_code` (fills the sidebar's
hard-coded "Demo Org"/"Developer"). `comments` = `{author, role, at, body}` by `entry_number`; system events have author
`System`, role `system`. `sources` = `{id?, title, url?}` by position; `id` only while the article is servable.

Lists and single reads use a fixed number of queries (no per-ticket query).

- `GET /tickets`: customer → their account's; agent → all. Newest `updated` first. Customer without account: 403.
- `GET /tickets/{id}`: other account → 404.
- `POST /tickets` (customer, 201): `{title, category, severity, description?, sources?, aiAnswer?, consent: true}`.
  title trimmed 1..2000; description ≤20000; aiAnswer ≤20000, blank = absent; ≤50 sources, title 1..500, url must be
  http(s) ≤2000; unknown category 422; unknown source id keeps the title and drops the id. Membership with
  `can_open_cases=false`: 403. Status `Submitted`. Event: `Escalated after the AI suggestion did not help` when
  aiAnswer is present, else `Case opened`.
- `POST /tickets/{id}/take` (agent): only if unassigned and status is submitted, in_progress or waiting_for_customer;
  else 409. Two simultaneous takers: exactly one 200, the other 409. Sets assignee and `In progress`.
  One event: `{name} took the case`.
- `POST /tickets/{id}/replies`: `{body, status?}`; body trimmed 1..20000.
  - Agent: status becomes `status` if given, else unchanged; if unassigned, assign to the agent (no extra event).
  - Customer (reporter only): sending `status` is 403. `Waiting for customer` or `Resolved` → `In progress`.
  - The reply precedes `Status changed to {status}`, which is added only if the status changed.
- `PATCH /tickets/{id}`: `{status?, assignee?, severity?}`; `status`/`severity` null is 422.
  - Agent: any. Events in this order, one per field that actually changed: `Status changed to {label}`,
    `Assigned to {name}` or `Unassigned`, `Severity changed to {label}`.
  - Customer (reporter only): any of `assignee`/`severity` present, or a status other than `Resolved`/`Submitted`: 403.
    `Submitted` is a reopen and valid only from `Resolved` (else 409, unless already `Submitted`).
    Events: `Customer marked the case resolved` / `Customer reopened the case`.
  - A patch that changes nothing returns the ticket untouched: no event, no `updated` or `version` change.

Every effective write locks the ticket row, and commits ticket + entries in one transaction, sets
`updated_at = clock_timestamp()`, increments `version`, and keeps `resolved_at` non-null exactly when resolved (keep the
original `resolved_at` when it was already resolved). System events record `actor_id` of the acting user, with
`actor_name_snapshot='System'`, `actor_role='system'`, `kind='event'` and an `event_type`.

## Structure

Follow the existing layers. Rules are pure functions (no DB) in the domain/application layer, so they unit-test
without PostgreSQL; the repository locks, calls the rule, and persists. Reuse `infrastructure/postgres/connection.py`.
Wire in `bootstrap.py`; domain errors map to HTTP in one place. No new dependencies.

`backend/sql/demo_identities.sql` (optional, rerunnable, **not** part of the required sequence) seeds the frontend's demo
people: account `Demo Org`; customers `customer` (Demo customer, Owner), `mina` (Mina Park, Member),
`jordan` (Jordan Lee, Read only, cannot open cases); agents `alex` (Alex Chen), `priya` (Priya Nair), `sam` (Sam Okafor);
emails as in `frontend/src/shared/api/demo/users.ts`, agents `<first>.<last>@support.demo.test`, company
`Support Copilot · Support engineering`. Rerunning must not overwrite profile edits.

## Acceptance

TDD: each behaviour above has a test that was seen failing first. Rules are unit-tested; endpoints are tested over HTTP
against a real disposable PostgreSQL (`EMBEDDING_TEST_DSN`), including cross-account 404, every 403, concurrent take,
event order, rollback of a failed write, NUL/overflow/malformed input, and `DEMO_AUTH` off. The existing suite stays
green and `ruff check` is clean. Update `.env.example`, `backend/README.md`, `backend/sql/README.md`, the Postman collection and the
API/Data-model/Gaps sections of `docs/frontend/pages-and-features.md`.

## Frontend wiring notes

Done on 2026-11-25. Articles are rendered with `react-markdown` and `remark-gfm`; HTML in them is shown as text.

Send `X-Demo-User` (`customer`/`alex`) from the role toggle; send `consent: true`; send `assignee: null` to unassign
(`JSON.stringify` drops `undefined`); map 404 to `null`; load `/agents` only for agents (route loader and sidebar);
format ISO `updated` and replace the `isRecent` regex; render `content` markdown.
