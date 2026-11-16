# Incremental Embedding Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Admit immutable knowledge revisions and process them with a local, leased PostgreSQL embedding queue, preserving the previous publication until replacement succeeds.

**Architecture:** Keep the current preparation/import commands unchanged. Application use cases depend on typed ports; psycopg repositories share explicit transaction connections, and bootstrap constructs a lazy Sentence Transformers encoder. A finite run-once worker uses claim tokens, independent heartbeats, and atomic publication.

**Tech Stack:** Python (currently >=3.14), psycopg 3, PostgreSQL 16/pgvector, Sentence Transformers/PyTorch, pytest, Ruff, uv.

**Spec:** [Approved implementation scope](../specs/2026-11-16-embedding-worker-design.md). The user's request to perform this spec supersedes its earlier spec-only delivery boundary.

## Global Constraints

- No model/dimension default: require an operator-selected identifier, immutable upstream commit revision, registry UUID, dimension, tokenizer limit and explicit document/query prompt rules.
- Preserve staging-only imports, existing API behavior and historical citation artifacts. No source fetches, model downloads, production migrations or scheduler installation during implementation.
- Existing uncommitted `backend/sql/001_schema.sql`, `002_embeddings.sql`, `003_seed_reference.sql`, SQL README, database design and health-test edits remain outside implementation commits.
- Add `backend/sql/004_embedding_jobs.sql` against the reviewed prerequisite schema; document that prerequisites must be applied separately by the migration owner. Verify only against disposable PostgreSQL instances.
- Preserve Python >=3.14 unless supported dependency resolution proves a change necessary; explicitly document any proposed compatibility change before making it.
- Lease 300 seconds, heartbeat 60 seconds, three attempts by default; require 0 < heartbeat < lease. Retry delay is `min(60 * 2**(attempts-1), 3600)` seconds.
- Database time controls leases/cutoffs; normalize vectors for cosine and reject nonfinite/zero/wrong-dimension results. Never silently truncate source text.
- Semantic configuration includes model registry identity/revision/dimension, cosine normalization, prompt rules, tokenizer limit, chunker version and policy; batch size/device/scheduling do not affect its hash.
- Use small coherent, passing commits. Never stage unrelated user work or rewrite history.

## Review Focus

1. Metadata with valid display labels but invalid IDs: accept known category labels/IDs deterministically; reject unknown values with batch rollback (Task 2).
2. Whitespace/Unicode and long unbroken strings: canonicalize only specified content conventions and never lose text while splitting; terminate even when heading/prompt overhead consumes capacity (Tasks 2–3).
3. Heartbeat connection failure or claim loss during inference: cancel persistence, leave recoverable work, never overwrite a newer owner (Tasks 1, 4).
4. Cross-configuration superseded jobs and document deactivation between claim/publication: retire without encoding or changing the prior publication (Tasks 1, 3–4).
5. Exceptions containing connection credentials or source bodies: log bounded safe codes/messages without raw exception strings (Tasks 2, 4–5).

## File and interface map

- `domain/embedding_job.py`: frozen configuration/job/chunk/result records, safe processing errors, canonical hashing and vector validation. Domain imports no adapters.
- `application/ports.py`: add `EncoderPort`, `ChunkerPort`, `EmbeddingStorePort`, and `LeasePort`; retain `LLMPort`.
- `application/use_cases/enqueue_embedding.py`: source validation, canonical snapshot creation, admission/retry orchestration.
- `application/use_cases/process_embedding_job.py`: bounded preparation/encoding, result validation and publication request.
- `infrastructure/postgres/connection.py`: connection factory and transaction context; database settings remain outside application code.
- `infrastructure/postgres/embedding_jobs.py`: claims, recovery, ownership fencing, retries, queue observations and safe transitions.
- `infrastructure/postgres/knowledge_repository.py`: atomic admission and artifact/publication persistence.
- `infrastructure/embeddings/chunker.py`, `sentence_transformer.py`: existing chunker adapter/token-safe refinement and shared lazy encoder.
- `interface/worker/main.py`, `enqueue.py`: CLI parsing, finite runner, heartbeat, interruption, summaries.
- `core/config.py`, `bootstrap.py`, `pyproject.toml`, `uv.lock`, `.env.example`: explicit configuration, adapter composition, dependencies and entry points.
- `tests/embeddings/`, `tests/worker/`, `tests/integration/`: fake-encoder unit tests and opt-in disposable PostgreSQL tests. Paths above are relative to `backend/src/support_copilot/` unless otherwise stated.

### Task 1: Persistence, processing identity and leased job queue

**Files:** Create migration, domain records, connection/queue adapters and `tests/integration/{conftest.py,test_embedding_jobs.py}`; extend ports and dependency metadata.

**Interfaces:** Define `EmbeddingConfig` (frozen semantic settings, `canonical_json()` and `config_hash`), `EmbeddingJob` (UUID identities, target generation, immutable config, attempts and claim token), `RecoveryResult`, and `QueueObservation`. Define `LeasePort.renew(job: EmbeddingJob) -> bool`; `EmbeddingStorePort.now() -> datetime`, `recover(cutoff: datetime) -> RecoveryResult`, `claim(config_hash: str, cutoff: datetime) -> EmbeddingJob | None`, `fail(job: EmbeddingJob, code: str, retryable: bool) -> str`, and `observe(config_hash: str, cutoff: datetime) -> QueueObservation`. All connections are short lived/context managed; heartbeat uses its own connection.

- [x] Write failing schema tests for both an empty disposable database and one with legacy staging rows, applying reviewed 001/002/003 only in the fixture. Assert rows survive and 004 adds generation/target constraints, composite ownership FKs, terminal/lease checks and indexes.
- [x] Write failing two-connection tests: concurrent claims yield distinct jobs; token rotation fences heartbeat/failure/persistence; exhausted recovery fails; retryable recovery sets availability to cutoff; later lease expiries are untouched. Test superseded jobs across configuration hashes and current jobs owned elsewhere.
- [x] Run `uv run pytest tests/integration/test_embedding_jobs.py -v` against a disposable pgvector PostgreSQL 16 container and confirm behavior fails before implementation. Require an explicit test DSN; never default to the development database or truncate its tables.
- [x] Add psycopg 3 binary driver dependency and resolve the lockfile. Implement 004 with requested-target invariants, queue checks/indexes and an immutability trigger for registry identities referenced by jobs. The trigger must serialize against concurrent job creation using registry row locks.
- [x] Implement database-time claims with `FOR UPDATE SKIP LOCKED`, attempt increments, fresh UUID tokens and committed leases. Establish document-before-job lock order for all operations needing both; recovery/retirement must use the same order and recheck state after locking. Fence every owner mutation with status, token and `clock_timestamp()` lease validity.
- [x] Run integration tests plus `uv run ruff check src tests`; commit only new/modified implementation files as `feat(ingestion): add embedding jobs and processing targets`.

### Task 2: Atomic immutable admission and explicit retry

**Files:** Create enqueue use case, knowledge repository admission methods, enqueue CLI and unit/integration admission tests; extend bootstrap and entry points.

**Interfaces:** `canonical_snapshot(document_id: str, payload: dict, categories: dict[str, str]) -> RevisionSnapshot`; `enqueue(store: EmbeddingStorePort, config: EmbeddingConfig, document_ids: list[str] | None) -> AdmissionResult`; `retry_failed(store: EmbeddingStorePort, job_id: UUID) -> None`. Add store methods `admit(config, document_ids)` and `retry_failed(job_id)` with whole-operation transactions; CLI selection uses mutually exclusive `--all`, repeatable `--document-id`, or `--retry-job`.

- [x] Write failing tests proving initial/identical admission, changed fetch timestamps ignored, sorted topics, metadata/config changes, A → B → A generation ordering and unchanged failed jobs preserved. Assert supplied content hashes are checked, unknown/missing metadata rejected, category display labels map to seeded IDs, and invalid URL/source/timestamps fail clearly.
- [x] Write PostgreSQL tests proving mixed valid/invalid selection rolls back all revisions/targets/jobs, unknown selected IDs fail explicitly, concurrent import/admission serializes and snapshots remain immutable. Retry must reject nonfailed, outdated and inactive targets and log prior safe diagnostics before clearing them.
- [x] Run `uv run pytest tests/embeddings/test_admission.py tests/integration/test_embedding_admission.py -v`; verify tests fail for missing behavior.
- [x] Implement canonical JSON with stable keys/UTF-8, normalized LF Markdown and recomputed SHA-256; preserve meaningful whitespace/code. Hash content plus the spec's semantic metadata only. Store the complete immutable payload and extracted relational fields; derive `excerpt` deterministically from content, use `display_body = NULL`. Require the existing document ID to agree with payload identity.
- [x] In a single batch transaction lock selected documents in document-ID order, validate everything, create/reuse revisions and compare requested revision/config. Increment generations only on target changes; return existing job/status otherwise. Keep model registry lookup/identity validation in this transaction. Do not load/download a model during admission.
- [x] Add CLI JSON counts and safe errors: rejected validation reports zero committed admissions, with rejected count; exit 2 for CLI/config issues, 1 for batch rejection/database failures, 0 for success. Run new tests and existing `tests/knowledge`; commit as `feat(ingestion): admit versioned embedding requests`.

### Task 3: Token-safe local encoding and atomic publication

**Files:** Create encoder/chunker adapters, processing use case, encoder/processing tests and PostgreSQL publication tests; extend settings/bootstrap and optional embedding dependencies.

**Interfaces:** `EncoderPort.token_count(text: str, *, query: bool = False) -> int`, `encode_documents(texts: list[str]) -> list[list[float]]`, `encode_queries(texts: list[str]) -> list[list[float]]`; `ChunkerPort.chunks(snapshot: RevisionSnapshot, config: EmbeddingConfig, encoder: EncoderPort) -> list[EmbeddingChunk]`; `process_job(store, job: EmbeddingJob, chunker, encoder, stopped: Callable[[], bool]) -> str`; store `load_snapshot(job) -> RevisionSnapshot`, `is_current(job) -> bool`, `publish(job, chunks, vectors) -> str`. `publish` returns completed/superseded or raises ownership loss.

- [x] Write failing fake-tokenizer tests for prompt overhead/default prompts, long unbroken text, Unicode, nested headings, empty body, oversized fences/tables and heading-only overflow. Assert no text is silently dropped, every emitted text fits including specials/prompt, deterministic IDs and preserved citation/heading metadata.
- [x] Write vector tests rejecting wrong dimensions, NaN/inf/zero/nonunit vectors and missing/extra output rows. Test configurable document token/chunk budgets before inference and bounded sequential encoding batches.
- [x] Write publication integration tests for newer generations, deactivation, stale/expired tokens, exact ownership/vector coverage, idempotent replay and forced SQL failure after artifact insertion. Assert prior publication remains and completion/publication commit together.
- [x] Run those tests and confirm missing implementation failures. Verify official PyTorch/Sentence Transformers documentation and actual uv wheel resolution for Windows/Linux Python 3.14 before selecting compatible dependency bounds; record results. Prefer a worker optional dependency group to keep API-only installations light. If unsupported, propose the specific Python change rather than silently changing it.
- [x] Implement a lazy pinned encoder with `trust_remote_code=False`, offline/local-only default, explicit device/batch settings and no implicit model fallback. Load once, validate actual dimension/tokenizer limit against effective config, registry and `chunk_embeddings.embedding` type modifier. Safe artifact-unavailable errors must explain provisioning without downloading.
- [x] Wrap the existing heading-aware chunker. Use actual tokenizer counts and prompt policy for iterative ordinary-text refinement; retain indivisible blocks or fail with a stable code. Assign deterministic final chunk IDs/indexes after splitting. Include refinement version/limits in config identity. Default budgets: 100,000 tokens, 2,000 chunks per document; batch size 32, all positive and configurable.
- [x] Implement final document-before-job transaction: revalidate live ownership/current active target; retire obsolete owned work; create/reuse set; persist deterministic chunks/vectors, verify complete exact coverage and finite normalized dimensions; ready set, publication upsert, current revision update and completion together. Repeat ownership/lease checks immediately before final state changes; rollback on loss.
- [x] Run encoder/processing/publication suites and Ruff; commit as `feat(embeddings): add local encoder and atomic publication`.

### Task 4: Finite run-once runner, heartbeat and summaries

**Files:** Create worker CLI/runner and heartbeat helper; extend settings/bootstrap/entry points and `tests/worker/{test_runner.py,test_cli.py}`.

**Interfaces:** `run_once(store: EmbeddingStorePort, encoder_factory: Callable[[], EncoderPort], chunker: ChunkerPort, config: EmbeddingConfig, stop: Event) -> WorkerSummary`; `WorkerSummary.exit_code -> int`. `main(argv: list[str] | None = None) -> int` requires `--once`. Bootstrap exposes `build_embedding_worker()` and `build_embedding_admission()` without importing model libraries into API startup.

- [x] Write failing runner tests for no work (zero encoder initializations), multiple documents (one initialization), initial cutoff, recovery eligibility, fresh failure deferred by backoff, later expiries deferred, exhausted recovery exit 1 and historical failures ignored. Assert configuration mismatches stay unclaimed and produce exit 1; owned-elsewhere work exits promptly with 0.
- [x] Add controlled heartbeat tests with an independent connection for successful renewals, token loss and database disconnection during inference. Assert no persistence after ownership becomes uncertain and stale owners cannot clear replacement claims.
- [x] Test SIGINT/SIGTERM between claims and during encoding, stop before publication, invalid CLI/config exit 2 and bounded shutdown. Include sanitized exception tests using credential/body sentinel strings; assert these never appear in emitted logs.
- [x] Run `uv run pytest tests/worker -v` and confirm failing behaviors. Implement database-cutoff startup recovery/retirement, matching-config claim loop, pre-encoding current-target checks and lazy model loading. Fail actual transient processing with backoff; permanent validation failures terminate immediately. Keep future retries separate from failures observed in this invocation.
- [x] Implement heartbeat stop/lost events and bounded join. Stop claiming on signal and prevent incomplete completion; native model calls may finish after interruption, but main can leave the lease to expire without persistence. Ensure no non-daemon inference/heartbeat work can make shutdown unbounded; document this limitation.
- [x] Emit structured logs with IDs, generation, config identity, attempts, durations, counts and safe transition/error codes. Summary includes completed/superseded/failed/recovered/deferred/blocked/owned-elsewhere, with exit rules from spec. Catch startup failures safely and restore signal handlers on exit.
- [x] Run runner/CLI and PostgreSQL lease suites; commit as `feat(worker): add run-once embedding runner`.

### Task 5: Operational documentation and complete verification

**Files:** Update `backend/README.md`, `backend/.env.example`; create `backend/docs/embedding-worker.md`, `backend/tests/integration/test_embedding_smoke.py` and evidence in `docs/superpowers/verification/2026-11-16-embedding-worker.md`. Do not edit the user's uncommitted SQL README.

**Interfaces:** Document the two console commands, explicit environment fields/defaults, migration prerequisites and runtime/migration-role separation. Smoke tests require explicit opt-in test DSN, model identifier/revision and preprovisioned cached artifacts.

- [x] Document migration order 001/003/002/004, runtime schema checks, selected model registration, offline provisioning as a separate operator action and coordinated rebuild/cutover. Provide SQL for oldest pending age, failed jobs and expired leases; retrieval must join active documents through publications using the same encoder/config.
- [x] Add PowerShell and cron examples for Asia/Bangkok daily execution, explicit working directory/env/logs, overlap prevention and dependency exit checks for prepare → import → enqueue → worker. Explain backoff eligibility versus the next scheduled invocation; examples install nothing.
- [x] Add explicit retry and recovery instructions, safe failure codes, exit statuses and interpretation of partial successes/owned-elsewhere/future retries. Ensure no examples contain real credentials or promise shared-queue emptiness.
- [x] Add opt-in smoke assertions: pinned model dimension/unit norm, first admission publishes, unchanged admission performs no encoding, changed content replaces publication, forced failure preserves old publication. Record Python/PyTorch/Sentence Transformers/model revision/OS/device when run. Report skipped smoke honestly if artifacts are unavailable; never download as a test side effect.
- [x] Run `uv run pytest -q` and `uv run ruff check src tests` from backend; run full disposable PostgreSQL suite on empty and staging-populated prerequisites. Record exact results and distinguish skipped integration/smoke checks from passes. Run `git diff --check` and inspect final diff/status for unrelated changes and secrets.
- [x] Review whole implementation against every numbered acceptance criterion, particularly lock ordering, lease expiry, prompt identity and transaction rollback. Fix findings and rerun the affected checks before claiming completion. Commit only documentation/smoke/evidence files as `docs(worker): document daily execution and recovery`.

## Plan review

Coverage: Tasks 1–2 cover persistence, admission and retries; Task 3 covers tokenizer/model validation and publication; Task 4 covers lifecycle/CLI/exit behavior; Task 5 covers operations and all verification evidence. All five review-focus conditions have assigned tests. Production schema state and selected model remain deployment inputs, not prerequisites for fake-encoder implementation. Real model smoke depends on artifacts provisioned by the operator.

Execution recommendation: native execution in this chat, with a final independent review, because the five tasks share tightly coupled transaction/port contracts. The writing-plans workflow requires user review of this plan and selection of execution method before implementation.

Execution completed on codex/embedding-worker. See ../verification/2026-11-16-embedding-worker.md for evidence, review fixes, deviations and skipped real-model smoke.
