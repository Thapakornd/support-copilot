# Incremental embedding worker

Date: 2026-11-16. Status: proposed design for review; implementation is not included.

## Intent and scope

Generate local document embeddings in a separate Python process, using PostgreSQL as a durable job queue. Run the worker once daily or manually, processing only admitted new or changed document revisions. Keep the last complete searchable revision available until its replacement is ready.

The user selected a Python backend/worker architecture and requested a project-specific spec with proper commit history. Daily scheduling, PostgreSQL jobs, and Sentence Transformers follow the preceding discussion. Exact model selection, operational settings, and the promotion boundary below are designer recommendations, not additional user approvals.

In scope: admission of immutable revisions, durable jobs, local encoding, chunk/vector persistence, atomic publication, retries, crash recovery, a run-once CLI, and operator documentation. Out of scope: a broker, gRPC/HTTP embedding service, continuous polling mode, a new document-management API/UI, changing chat retrieval, automated scraping schedules, model fine-tuning, and applying migrations or downloading models as part of writing this spec.

## Current project and prerequisites

- `backend/src/support_copilot/` has domain, application, infrastructure, and interface layers. `bootstrap.py` constructs concrete dependencies.
- `knowledge/prepare.py` normalizes documents and makes deterministic heading-aware chunks. The default 2,400-character target is not a tokenizer limit. Code fences and tables can exceed it.
- `knowledge/import_documents.py` validates JSONL and invokes Docker Compose/psql to upsert `knowledge_documents(document_id, data)`. It does not enqueue jobs or create immutable revisions.
- `docker-compose.yaml` supplies PostgreSQL 16 with pgvector. The database design and SQL working files describe revisions, chunk sets, model registration, embeddings, and retrieval publications, but are not proof these tables are deployed.
- `backend/pyproject.toml` currently requires Python >=3.14 and has no Sentence Transformers or Python PostgreSQL driver dependency. Verify supported Python/PyTorch wheels on the target Windows/Linux environment before pinning dependencies. Any Python-version change must be explicit in the implementation and documentation.

Reference: [database schema design](2026-11-14-database-schema-design.md). This feature uses its knowledge tables and publication semantics, not its unrelated ticket/account implementation. Review the actual applied schema before preparing additive migrations; do not silently rewrite existing SQL working files or assume their deployment.

## Approaches and decision

| Approach | Benefit | Cost | Decision |
|---|---|---|---|
| Encode synchronously during imports/API requests | Fewest moving parts | Caller waits; processing competes with request handling | Rejected for background ingestion |
| Python worker + PostgreSQL jobs | Durable background processing; shares existing infrastructure | Job leases and retries are application responsibilities | Selected proposal |
| Separate inference service with gRPC, optionally a broker | Shared model/GPU and independent inference scaling | Network contract, service operations, and more failure handling | Deferred until required |

The API and worker share a codebase, but run as separate processes. The worker loads one model instance per invocation and reuses it across jobs. PostgreSQL contains the durable command, not a transient in-memory event. A broker or outbox dispatcher is unnecessary because admission and queue insertion share one transaction.

## Admission and change detection

Preserve the current importer's staging-only behavior. Introduce `support-copilot-enqueue-embeddings` to promote selected staging payloads into immutable processing requests. This follows the existing database design's staging/promotion boundary and replaces the earlier conversational suggestion to enqueue automatically from every staging import. A future document-publishing API should call the same admission use case; do not add such an endpoint in this feature.

For each document, admission locks its row, validates the staging payload and normalized category/source metadata, recomputes the content hash, and computes a revision hash from canonical JSON. Hash normalized content plus title, citation URL, product, deployment, version scope, category, topics, and source type. Exclude fetch timestamps and transport-only metadata; sort topic values for hashing. Do not trust a supplied hash without checking it. Existing generic importer compatibility is retained; promotion can reject incomplete payloads with a clear validation error.

In one transaction for the selected batch:

1. Create/reuse `knowledge_document_revisions` by `(document_id, revision_hash)` with an immutable source snapshot.
2. Compare the revision and effective processing configuration with the document's latest requested target.
3. If unchanged, return the existing job/status without new encoding or resetting a terminal failure. Explicit retry is a separate operation.
4. Otherwise increment the document's ingestion generation, record the new requested revision/configuration, and insert a pending job for that generation.

Serialize imports and admission through ordinary row locks/updates. Snapshot the staging payload under that lock. An import arriving afterwards remains staged until the next admission. Reverting A -> B -> A creates a new generation even when an existing revision is reused. Generation order represents admission order; source timestamps are not ordering authorities.

The worker reads only its immutable revision, never the mutable `data` JSONB payload. A metadata-only change creates a revision/job; version one may regenerate all its document embeddings. Cross-revision chunk/vector caching is deferred.

For initial existing staging rows, the admission command creates the first jobs. Documents absent from a partial import stay active. Do not infer deletion from absence; if a document is explicitly deactivated, publication is blocked and retrieval must exclude it.

## Persistence additions

Extend `knowledge_documents` with `requested_revision_id uuid?`, `ingestion_generation bigint NOT NULL DEFAULT 0 CHECK >= 0`, and `requested_embedding_config_hash text?`. A composite FK `(document_id, requested_revision_id)` points to revisions `(document_id, id)`; constraints require all requested-target fields to be present when generation > 0. `current_revision_id` retains its existing meaning: the successfully promoted revision, not the pending target.

Create `embedding_jobs`:

| Fields | Contract |
|---|---|
| `id uuid PK`, `document_id text`, `revision_id uuid`, `generation bigint CHECK > 0` | Composite revision FK enforces document ownership; UNIQUE `(document_id, generation)` |
| `model_id uuid FK embedding_models`, `chunker_version text`, `config_hash text`, `config jsonb` | Immutable processing identity and canonical effective configuration |
| `status text` | CHECK in `pending`, `processing`, `completed`, `failed`, `superseded` |
| `attempts integer DEFAULT 0`, `max_attempts integer DEFAULT 3` | CHECK attempts >= 0 and max_attempts > 0 |
| `available_at timestamptz` | Earliest permitted next claim |
| `claim_token uuid?`, `lease_expires_at timestamptz?` | Present exactly while processing; new token on every claim |
| `last_error_code text?`, `last_error text?` | Bounded, sanitized diagnostic details |
| `created_at`, `updated_at`, `finished_at?` | UTC instants; finished_at present exactly for terminal statuses |

Index pending jobs by `(available_at, created_at, id)` with a pending predicate, and processing jobs by lease expiry. Index FK lookup paths where not already covered.

`config_hash` is SHA-256 of canonical effective JSON including model registry identity, immutable model revision, output dimension, cosine normalization, query/document prompt rules, tokenizer limit, chunker version, and chunking parameters. Store this configuration in the job so a later deployment cannot reinterpret queued work. Batch size/device and scheduling settings do not change semantic identity. Model registry entries used by jobs are immutable.

Reuse existing chunk-set uniqueness `(revision_id, chunker_version, config_hash)`; including the encoding configuration in this hash deliberately isolates incompatible outputs. Embeddings remain keyed by `(chunk_set_id, chunk_id, model_id)`.

Choose one model/dimension for the initial corpus and use matching `vector(D)` storage. Model identifier and immutable upstream commit revision are required deployment configuration; there is no silent default. E5-small is a candidate, not a selected dependency. The implementation must validate the registered dimension against actual model output and the applied pgvector schema before processing. A model change requires a coordinated corpus rebuild/cutover; live mixed-model retrieval is outside scope.

## Worker lifecycle and recovery

`support-copilot-worker --once` processes claimable supported jobs eligible at invocation start and exits. Capture a database-time cutoff; only jobs created/available by that cutoff qualify. This prevents a steady stream of new jobs or delayed retries from keeping a daily invocation alive indefinitely. Check for superseded targets before loading the model; initialize it lazily before the first actual encoding job.

Each invocation supports exactly the effective model/encoding/chunking configuration resolved at startup. Claim only jobs with its matching configuration hash. Current targets with other configurations remain untouched and are reported as blocked configuration mismatches with exit 1; the worker never silently substitutes settings or switches models. An operator can run a matching configured worker or explicitly admit a new target configuration. Superseded jobs can be retired regardless of configuration. This supports controlled deployment changes without a mixed-model serving promise.

Do not wait for jobs owned by another live worker. When no supported pending jobs are claimable, exit and report the count observed as owned elsewhere; this alone is a successful exit, not proof the shared queue is globally empty. Recover only leases already expired at the initial cutoff during the startup recovery pass. Recovered retryable jobs whose creation predates the cutoff get `available_at = cutoff`, making them eligible in this invocation. Leases expiring later are left for the next invocation. Retrying an actual processing failure always uses fresh backoff and is deferred.

1. Recover expired processing jobs: lock them, clear ownership, and reschedule as pending if attempts remain; otherwise mark failed. Superseded generations become superseded without encoding.
2. Claim one eligible pending job using a short transaction and `FOR UPDATE SKIP LOCKED`. Increment attempts, set status processing, generate a claim token, set the lease, and commit.
3. Prepare chunks and encode outside database transactions. Start with one job and bounded sequential batches; no model-per-job reload or unbounded parallel inference.
4. Renew the lease from an independent database connection while work is running. All renewals and mutations require the matching claim token and unexpired lease, using database time. Stop writes if ownership is lost.
5. Commit result persistence, publication, and job completion in one short final transaction as described below.

Proposed settings: 300-second lease, renewal every 60 seconds, three attempts, retry delay `min(60 * 2^(attempts-1), 3600)` seconds. Values are configurable and validated so renewal is shorter than the lease. A daily worker does not wake when backoff expires; retries wait for the next invocation unless manually run sooner. Document this distinction clearly.

Transient database/encoding resource failures reschedule with backoff. Invalid source structure, incompatible model/configuration, and unprocessable oversized blocks fail with actionable codes rather than silently dropping text. Exhausted retries are terminal. Provide an explicit CLI retry operation restricted to failed jobs: reset attempts/availability and clear terminal fields, only if the target remains current; preserve prior error details in structured logs before clearing. Future audit-history persistence is optional.

On SIGINT/SIGTERM, stop claiming new jobs, attempt a bounded clean stop, and release or let the lease expire. Never report an unfinished job as completed. A crash can cause repeated computation; result persistence must remain idempotent.

## Chunking, encoding, and atomic publication

Reuse the existing heading-aware chunker through an application port or adapter. Add tokenizer-aware validation using the actual model tokenizer and document prompt overhead. Split ordinary text further when necessary, preserving heading and citation metadata. Code fences/tables that cannot fit intact fail explicitly in version one. No silent truncation. Hash the effective chunking policy and version so changing it creates a new target configuration.

Use a shared encoder adapter for document encoding and future query encoding, including model-specific prefixes/instructions. Do not prefix twice when model defaults already supply prompts. Require normalized finite nonzero vectors of the registered dimension and at least one nonempty chunk. The model must come from an operator-approved identifier and pinned revision; do not enable remote model code by default. Fail startup clearly when required cached artifacts are missing in offline mode. Download/provision artifacts explicitly before scheduling production runs.

For the current small corpus, keep generated batches in bounded document-level memory and write all document artifacts in the final transaction. Add a configurable maximum per-document token/chunk budget; reject over-budget documents clearly. Durable batch checkpoints and large-document streaming writes are deferred.

The final transaction locks the document and job in a consistent order, then:

- Verifies processing status, claim token, live lease, document active state, requested revision, generation, and configuration hash.
- Marks outdated work superseded without changing the publication. An expired owner cannot persist results or change job state.
- Creates/reuses the matching chunk set; writes deterministic chunks/embeddings idempotently and validates exact chunk/vector coverage, ownership, dimensions, and vector validity.
- Sets the chunk set ready and replaces `retrieval_publications` for that document; updates `current_revision_id` and completes the job together.

Rollback leaves the old publication and job recoverable. Unpublished failed work never becomes searchable. Historical revisions/sets referenced by citations are retained. A publication is a retrieval pointer; it does not mean mutable staging data was automatically approved. Future retrieval must join active documents through publications and encode queries with the same model/configuration.

## Code placement and interfaces

```text
backend/src/support_copilot/
  bootstrap.py                         # add worker/admission dependency builders
  core/config.py                       # DB, model, lease, batch and size settings
  domain/embedding_job.py               # job/target state and immutable configuration
  application/ports.py                 # transaction, job, knowledge, chunker, encoder ports
  application/use_cases/
    enqueue_embedding.py               # validate snapshots + transactionally admit jobs
    process_embedding_job.py            # prepare/encode/persist/publish orchestration
  infrastructure/
    embeddings/sentence_transformer.py  # tokenizer, prompts, local encoder
    postgres/
      connection.py                    # driver, transaction and connection management
      embedding_jobs.py                # claims, leases, retries and fencing
      knowledge_repository.py          # revisions, chunks, vectors and publication
  interface/worker/
    __init__.py
    main.py                            # --once runner and structured summary
    enqueue.py                         # admission CLI and explicit failed-job retry
  knowledge/                           # retain existing file preparation/staging commands
```

Use a normal Python PostgreSQL driver/pool (recommended: psycopg 3), not one Docker subprocess per worker operation. The transaction boundary must span related repository writes on the same connection. Do not expose infrastructure classes to domain/application code; `bootstrap.py` constructs the adapters. Exact port method names are left to the implementer.

## Commands, scheduling, and operations

Proposed project entry points, run from `backend/`:

```powershell
uv run support-copilot-enqueue-embeddings --all
uv run support-copilot-enqueue-embeddings --document-id <id>
uv run support-copilot-enqueue-embeddings --retry-job <uuid>
uv run support-copilot-worker --once
```

Selection flags are mutually exclusive; require one explicitly. Enqueue returns counts of admitted, unchanged, and rejected documents and fails the selected batch atomically on validation errors. Retry rejects nonfailed or superseded targets. Worker exits 0 when it has no further claimable supported work (including no work or jobs owned elsewhere), 1 on processing failures/deferred retries/newly exhausted recoveries/configuration-blocked eligible jobs observed during that invocation, and 2 on invalid CLI/configuration. Nonzero does not mean successful jobs were rolled back. Report pending future retries separately; do not fail forever because of historical failures outside the invocation's work.

For daily operation, Windows Task Scheduler or Linux cron starts the command in the correct working directory with an explicit environment and logs. The operator selects the daily time and timezone; document Asia/Bangkok examples without silently installing a schedule. Admission must precede worker execution. If source refresh is desired, the scheduled wrapper runs prepare -> import -> enqueue -> worker, aborting dependent steps when an earlier command fails. Automatically fetching sources or enabling a scheduler is not part of this feature.

A worker invocation alone never discovers changes still present only at the external source or unadmitted staging payloads. Jobs and leases permit safe overlapping manual/scheduled runs, though scheduler configuration should also avoid unintended overlap. Database timezone calculations use UTC instants regardless of scheduler timezone.

Log job/document/revision IDs, generation, configuration identity, attempt, duration, chunk count, state transitions and sanitized error codes. Do not log document bodies, vectors, credentials, or complete connection strings. Summaries distinguish completed, superseded, failed, recovered, and deferred jobs. Document queries for backlog age, failed jobs, and lease expiry. Use a migration owner for DDL and a runtime role with only required data access; secrets come from environment/configuration.

## Acceptance and verification

Use fake encoders for orchestration tests and a disposable PostgreSQL instance for locking/transaction tests. No paid calls or routine model downloads in the test suite.

1. Initial admission creates immutable revisions and one job per document; identical admission, even with a new fetched_at, adds no jobs. Metadata/content/configuration changes create new generations; A -> B -> A is handled correctly.
2. Invalid batch admission rolls back revisions, targets, and jobs together. Existing staging import/prepare commands retain their behavior.
3. Two workers cannot claim the same job concurrently. Expired leases recover; an old claim cannot heartbeat, write vectors, publish, or complete after reassignment.
4. A newer admitted generation prevents an older job from publishing, regardless of completion order. Deactivated documents cannot publish.
5. A failed final transaction leaves the previous publication intact. Retrying cannot duplicate chunks/vectors or expose incomplete sets. Completion and publication commit together.
6. Wrong dimensions, NaN/zero vectors, empty documents, prompt overhead, oversized code/table blocks and document budgets fail explicitly without silent truncation.
7. `--once` exits with no work, respects its cutoff, does not spin on backoff, and recovers exhausted jobs. Prove startup-recovered jobs are eligible, later lease expiries are deferred, owned-elsewhere work does not block exit, and mismatched configurations remain unclaimed with a blocked summary. Retry and exit-code behavior match the documented contract.
8. Fake-encoder tests prove one model initialization per useful invocation. Verify CLI/configuration errors and graceful interruption without marking partial work complete.
9. Run an opt-in smoke test with a provisioned pinned model and a tiny corpus: output dimension/normalization match the registry, repeat admission does no encoding, a changed document replaces its publication, and a forced failure preserves the old one. Record Python, PyTorch, Sentence Transformers, model revision, OS and device.

Run existing backend tests and Ruff plus the new unit/integration suites during implementation. Verify additive SQL against an empty supported schema and one with existing staging rows, with no production data changes. Run-once smoke testing does not install a persistent worker or daily schedule.

## Delivery and commit boundaries

This request delivers and commits this spec only. Existing uncommitted SQL, database design, and test changes are excluded. The spec is proposed for user review; a commit does not imply deployment or approval of every designer choice.

Future implementation should use small coherent commits, each with the corresponding meaningful tests:

1. `feat(ingestion): add embedding jobs and processing targets` — additive migration, driver/repositories, transaction and lease tests. Establish schema prerequisites explicitly.
2. `feat(ingestion): admit versioned embedding requests` — admission/retry CLI, hash/config identity, atomic enqueue and compatibility tests.
3. `feat(embeddings): add local encoder and atomic publication` — pinned model configuration, tokenizer validation, processing use case and publication tests.
4. `feat(worker): add run-once embedding runner` — bootstrap, heartbeat/recovery, exit summaries and runner tests.
5. `docs(worker): document daily execution and recovery` — setup, scheduler examples, model provisioning, manual retry, and recorded smoke-test evidence.

Do not split commits merely by file or commit failing intermediate states. Do not bundle unrelated SQL/test changes, rewrite existing history, apply migrations, download models, or install schedules without the corresponding implementation scope. Before implementation, approve this design and turn the agreed scope into an executable plan.
