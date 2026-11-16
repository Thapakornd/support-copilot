# Incremental local embeddings

The importer writes mutable staging JSON only. Admission snapshots selected documents
and creates durable jobs. `--once` processes admitted work eligible at its initial
database-time cutoff, then exits. A complete previous publication stays available
until its replacement commits. Chat retrieval is unchanged by this feature.

## Installation and schema prerequisites

Use Python 3.14 and PostgreSQL 16 with pgvector. From `backend/`:

```powershell
uv sync --extra embeddings
```

The API-only installation can omit `--extra embeddings`. The optional dependency
is Sentence Transformers 5.x; uv.lock records its resolved dependencies. No model
is selected or downloaded by installation or tests.

Review `sql/001_schema.sql`, `003_seed_reference.sql`, and `002_embeddings.sql`
with your migration owner. These are existing prerequisite working files, not
automatically deployed or included in the worker feature commits. Apply 001, seed
003, select/register the actual model, and apply 002 with that model's dimension.
Apply the additive `004_embedding_jobs.sql` once afterward. Track migration
application externally; these are one-time scripts. The migration works with the
reviewed knowledge schema and retains legacy staging rows. Do not run it against
an arbitrary differently versioned schema. Bootstrap never executes DDL.

Use a migration owner for DDL; use a separate runtime role with schema usage and
SELECT on categories/models, SELECT/UPDATE on knowledge_documents,
SELECT/INSERT on knowledge_document_revisions, knowledge_chunks and chunk_embeddings,
and SELECT/INSERT/UPDATE on knowledge_chunk_sets, retrieval_publications and embedding_jobs.
Additionally grant `UPDATE(is_active)` on embedding_models: PostgreSQL requires an
UPDATE privilege for the `FOR SHARE` row lock used to serialize model validation
against identity changes. This narrowly scoped grant permits activation changes,
but does not permit edits to model identifiers, revisions or dimensions. For example,
as the migration owner (substitute your already-created runtime role):

```sql
GRANT USAGE ON SCHEMA public TO embedding_runtime;
GRANT SELECT ON categories,embedding_models TO embedding_runtime;
GRANT UPDATE(is_active) ON embedding_models TO embedding_runtime;
GRANT SELECT,UPDATE ON knowledge_documents TO embedding_runtime;
GRANT SELECT,INSERT ON knowledge_document_revisions,knowledge_chunks,chunk_embeddings TO embedding_runtime;
GRANT SELECT,INSERT,UPDATE ON knowledge_chunk_sets,retrieval_publications,embedding_jobs TO embedding_runtime;
```

The importer has its own existing database connection mechanism. UUIDs are
application-generated; the worker requires no sequence or DDL privileges.

Choose a model whose licensing, tokenizer, prompts and dimensions you have
reviewed. Register its real UUID, provider `sentence-transformers`, identifier,
40-character upstream commit, output dimension, distance_metric `cosine`, and
is_active `true` in embedding_models. Referenced model identities cannot be edited;
register a new identity for a change. A dimension change requires a coordinated
schema/corpus rebuild and serving cutover. Concurrent mixed-model serving is outside
scope. Never register placeholder models in production.

## Required environment

Set these in the backend `.env` or process environment. Keep secrets out of logs:

```dotenv
EMBEDDING_DATABASE_URL=postgresql://runtime_user:password@127.0.0.1:5432/support_copilot
EMBEDDING_MODEL_ID=<registered UUID>
EMBEDDING_MODEL_NAME=<approved Hugging Face identifier>
EMBEDDING_MODEL_REVISION=<40-character immutable upstream commit SHA>
EMBEDDING_DIMENSIONS=<registered output dimension>
EMBEDDING_TOKENIZER_LIMIT=<reviewed total input-token limit>
EMBEDDING_DOCUMENT_PROMPT="<explicit document prefix, or empty string>"
EMBEDDING_QUERY_PROMPT="<explicit query prefix, or empty string>"
EMBEDDING_OFFLINE=true
EMBEDDING_DEVICE=cpu
```

Prompt strings are required even when empty. They override model default prompts
explicitly, so the prefix is applied once. Token counting includes the prompt and
special tokens, and uses the actual model tokenizer without truncation. The
configured limit must not exceed the model's supported limit. Query encoding
shares the same adapter but is not wired into the chat endpoint yet.

Defaults: lease 300 seconds, heartbeat 60 seconds, maximum attempts 3, inference
batch size 32, document budget 100000 tokens / 2000 chunks, character target 2400.
Override with `EMBEDDING_LEASE_SECONDS`, `EMBEDDING_HEARTBEAT_SECONDS`,
`EMBEDDING_MAX_ATTEMPTS`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_DOCUMENT_TOKENS`,
`EMBEDDING_MAX_DOCUMENT_CHUNKS`, and `EMBEDDING_TARGET_CHARS`. Values must be
positive, character target >=100, heartbeat < lease. Device and batch size do
not affect processing identity; model, prompt, tokenizer and chunking policy do.

Provision the **exact pinned model's complete artifacts** in the host's Hugging
Face cache before scheduling production runs, using your approved artifact
download process. The worker is local-only by default and leaves network/model
provisioning to the operator. An intentional `EMBEDDING_OFFLINE=false` permits
the library's download behavior; it is not needed for scheduled offline operation.
Missing artifacts or optional libraries produce `model_unavailable`; provision
them, then explicitly retry the current failed job. No remote model code is enabled.

## Manual operation

From `backend/`, after preparing/importing source data:

```powershell
uv run support-copilot-enqueue-embeddings --all
uv run support-copilot-enqueue-embeddings --document-id doc_abc --document-id doc_def
uv run --extra embeddings support-copilot-worker --once
uv run support-copilot-enqueue-embeddings --retry-job <failed-job-uuid>
```

Choose exactly one admission selection. A selected batch validates and commits
atomically; invalid metadata rejects it without partial admission. Unknown IDs
are errors. Existing manifest category aliases Authentication → security and
Performance → performance are accepted alongside seeded labels and IDs. Unknown
categories/source types are rejected. Source types normalize to documentation,
knowledge_article or resolved_case. Fetch timestamps/transport URLs are excluded
from semantic hashing; topics are sorted. Content hashes are recomputed and checked.

Identical admission adds no work, including for terminal failures. Content,
citation metadata or semantic configuration changes create a new generation.
Reverting to older content reuses its immutable revision but gets a new generation.
Retry only resets a **failed, still-current, active** target; old diagnostics are
logged as safe codes before clearing. Partial source imports do not deactivate
missing documents. Set is_active=false explicitly to block new publication.

Ordinary text is split further to fit tokens. Oversized fenced code/tables,
excessive heading/prompt overhead, empty documents and document budgets fail
explicitly (`oversized_block`, `heading_overhead`, `empty_document`,
`document_budget`). Vector coverage, finite/nonzero/unit norms and dimensions
are checked before publication. Registry/schema mismatches block operation.
Old publication pointers remain intact after any failed final transaction.

Worker JSON summary distinguishes completed, superseded, failed, recovered,
rescheduled, deferred, blocked, owned_elsewhere, ownership_lost and interrupted.
Exit 0 means no further eligible supported work was claimable, including when
another worker owns jobs. It does not mean the shared queue is empty. Exit 1
means a processing failure, newly exhausted recovery, deferred failure retry,
configuration blockage or interruption was observed. Existing historical failures
and future retries alone do not poison every subsequent invocation. Exit 2 means
invalid CLI/environment configuration. Successful earlier jobs remain committed
even when the overall invocation fails. Admission exits 1 for rejected batches or
database failures, 2 for invalid CLI/configuration, and 0 for success.

Expired leases at startup are recovered with availability equal to that run's
cutoff. Later expiries are left for a later invocation. Actual processing failures
retry after `min(60 * 2^(attempts-1), 3600)` seconds while attempts remain. **Backoff
does not start another worker**: daily operation waits until the next scheduled
run unless an operator runs it sooner. A matching configured worker is needed
for blocked configuration hashes, or explicitly admit a new target configuration.

On SIGINT/SIGTERM the worker stops claiming, stops heartbeat renewal and exits
without waiting indefinitely for native model inference. An unfinished claim is
left to expire; a daemon inference thread checks cancellation before publication.
Completed atomic transactions remain completed. Ownership uncertainty prevents
further owner writes. A crash may repeat computation but cannot expose partial sets.

## Daily execution examples (operator installs separately)

Choose the daily time/timezone explicitly. For Windows Task Scheduler on a machine
configured for Asia/Bangkok, an example is daily 02:00, Start in
`D:\individual-project\support-copilot\backend`, launch a PowerShell wrapper with
an explicit environment and a protected log directory. Set “Do not start a new
instance” for overlap control; queue leases also protect overlapping manual runs.
After creating the log directory and arranging environment secrets, wrapper example:

```powershell
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'D:\individual-project\support-copilot\backend'
# Omit prepare/import if source refresh is not intended for this schedule.
uv run support-copilot-prepare-knowledge
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run support-copilot-import-documents
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run support-copilot-enqueue-embeddings --all
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run --extra embeddings support-copilot-worker --once >> 'D:\protected-logs\embedding-worker.log' 2>&1
exit $LASTEXITCODE
```

Linux cron supporting CRON_TZ, with `/srv/support-copilot/backend/worker.env`
restricted to its service user and containing shell-quoted exports:

```cron
CRON_TZ=Asia/Bangkok
0 2 * * * /usr/bin/flock -n /srv/support-copilot/worker.lock /srv/support-copilot/run-embeddings.sh >> /srv/support-copilot/worker.log 2>&1
```

`run-embeddings.sh` example (explicit absolute uv installation path):

```sh
#!/bin/sh
set -eu
cd /srv/support-copilot/backend
. ./worker.env
/opt/uv/bin/uv run support-copilot-enqueue-embeddings --all
/opt/uv/bin/uv run --extra embeddings support-copilot-worker --once
```

Check your cron implementation's timezone support. All database comparisons use
UTC instants regardless of scheduler timezone. Worker execution alone discovers
neither external source changes nor unadmitted staging updates. These examples
do not install schedules or enable automatic scraping.

## Diagnostics and retrieval contract

Logs contain identities, attempt/configuration and safe codes, never source
bodies, vectors, passwords or full connection strings. Database operations have
bounded statement/lock/connect timeouts. Use these read-only diagnostics:

```sql
SELECT count(*) AS pending, min(created_at) AS oldest,
       clock_timestamp()-min(created_at) AS oldest_age
FROM embedding_jobs WHERE status='pending';
SELECT id,document_id,generation,attempts,last_error_code,finished_at
FROM embedding_jobs WHERE status='failed' ORDER BY finished_at DESC;
SELECT id,document_id,lease_expires_at FROM embedding_jobs
WHERE status='processing' AND lease_expires_at<=clock_timestamp();
SELECT config_hash,status,count(*) FROM embedding_jobs
WHERE status IN ('pending','processing') GROUP BY config_hash,status;
```

Future retrieval must start from active knowledge_documents joined through
retrieval_publications, ready chunk sets, chunks and embeddings for that exact
model/configuration. Do not retrieve every historical chunk or the mutable
staging payload. Keep historical revisions/sets for citations.

## Verification

Regular unit tests use fake encoders. PostgreSQL tests create unique disposable
databases on the supplied test cluster; the supplied database itself is never
truncated or dropped. Use a dedicated test cluster with CREATEDB privileges:

```powershell
$env:EMBEDDING_TEST_DSN='host=127.0.0.1 port=55439 dbname=embedding_worker_test user=postgres password=embedding_test_only'
uv run pytest -q
uv run ruff check src tests
```

Without the DSN, integration tests are skipped explicitly. The fixture tests empty
and staging-populated schema paths; no production database fallback exists.
For a real-model smoke, provision approved artifacts, install the embeddings extra,
set all EMBEDDING model/prompt fields above, and opt in:

```powershell
$env:EMBEDDING_MODEL_SMOKE='1'
uv run --extra embeddings pytest tests/integration/test_embedding_smoke.py -q -s
```

It forces offline loading, tests first/unchanged/changed admission and forced
publication rollback, and prints Python/PyTorch/Sentence Transformers/revision/
OS/device evidence. Missing configuration or artifacts fails this opt-in test;
it never silently downloads. See the repository verification record for results
actually obtained during implementation.
