# Import documents JSONL

User-authorized scope: add a script importing the existing documents.jsonl into
PostgreSQL, matching knowledge_chunks' ID plus JSONB layout. Keep the full record
in data, with document_id as the primary key. No changes to chunks or embeddings.

Approach: use the existing Docker Compose PostgreSQL service and psql through a
Python CLI (no new dependencies). Validate the entire input first, then use CSV
COPY into a temporary JSONB staging table and upsert in one transaction. This is
simpler for this local demo than adding a new database driver/configuration layer.
Resolve paths from the module so commands work from any directory. Provide a
dry-run that validates input without database access.

- [x] Write and run failing tests for validation, COPY encoding, dry-run, failures.
- [x] Implement the CLI, add the entry point, and document its commands.
- [x] Validate the real 16-document file; run tests and lint. Do not import into
  the user's database as part of script creation.

Verification: 47 backend tests pass; Ruff passes; installed command dry-run validates all 16 real documents. Fresh review found JSONB-incompatible Unicode validation gap; four regression cases failed first, then pass after validating all strings and keys. No database import executed.
