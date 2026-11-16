# Embedding worker verification — 2026-11-16

Implementation branch: `codex/embedding-worker`, based on `225f177`.

## Environment and dependency evidence

- Python 3.14.8, Windows 11 x86-64 (build 26200); psycopg 3.3.9.
- Disposable Docker PostgreSQL 16.16 (Debian x86-64), pgvector 0.8.7.
- No operations on the development database. Each integration case creates and
  drops its own UUID-named test database; test role cases create/drop unique roles.
- Python 3.14 binary-only dependency resolution succeeded for both
  x86_64-pc-windows-msvc and x86_64-unknown-linux-gnu using `uv pip compile
  backend/pyproject.toml --extra embeddings --python-version 3.14
  --python-platform <platform> --only-binary :all:`.
- Resolved optional runtime: Sentence Transformers 5.7.0, PyTorch 2.15.0,
  Transformers 5.23.0, tokenizers 0.23.3. This proves wheel resolution, **not**
  model-runtime execution or GPU compatibility. No optional model runtime or
  model artifacts were downloaded for the test suite.
- Adapter API/pinning behavior checked against the official
  [SentenceTransformer reference](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)
  and platform compatibility against the official
  [PyTorch installation guide](https://pytorch.org/get-started/locally/).

## Checks and results

The test command was the installed backend environment's equivalent of
`uv run pytest -q`, with `EMBEDDING_TEST_DSN` set to the disposable cluster:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Final result: **143 passed, 2 skipped**. The two skipped cases are the explicitly
opt-in real-model smoke, parametrized over empty and legacy-staging schema setup.
The suite emits 13 existing LangSmith `asyncio.iscoroutinefunction` deprecation
warnings, also present in the 47-test baseline. They are dependency warnings,
not worker test failures.

All new/modified implementation and test files pass Ruff. Full-backend Ruff was
also run and still reports four pre-existing I001 import-order errors in:

- `backend/src/support_copilot/interface/api/routes/chat.py`
- `backend/tests/knowledge/test_import_documents.py`
- `backend/tests/knowledge/test_pipeline.py`
- `backend/tests/knowledge/test_prepare.py`

Those unrelated files remain untouched. `git diff --check` passes (Git emits its
normal Windows LF/CRLF conversion notices). Both installed console entry points'
`--help` commands succeed. Actual Python CLI subprocess tests verify no-work exit
0, admission/unchanged counts, blocked-configuration exit 1, atomic rejection and
explicit failed-job retry.

## Functional coverage

- Empty and legacy-staging schema paths retain source rows and enforce target,
  ownership, status/lease and terminal-state constraints. Existing 001/003 scripts
  are applied in disposable databases. The fixture creates the test vector table
  at dimension 3 from 002's SQL contract; it does not execute 002's psql variable
  wrapper. No deployed schema state is inferred from these tests.
- Concurrent workers claim distinct jobs. Expiry recovery rotates tokens; stale
  owners cannot renew/fail/publish. Exhaustion, later-than-cutoff expiry and
  database-time eligibility behave as specified.
- Initial/unchanged/metadata/config changes, sorted topics, category aliases,
  forged hashes, A → B → A generations, immutable snapshots after later staging
  imports, unknown IDs, whole-batch rollback and explicit retry are covered.
- Token-aware Unicode/unbroken text splitting, significant boundary whitespace,
  indentation, prompts/special-token overhead, oversized fences/tables, empty
  documents and chunk/token budgets are tested without downloading a model.
- Wrong dimensions, missing/extra rows, NaN/inf, zero and nonunit vectors fail.
  Pinned revision, offline loading, disabled remote code, explicit document/query
  prompts and one lazy model initialization are checked at the library boundary.
- Atomic publication, newer-generation/deactivation fencing, forced SQL rollback,
  repeat persistence and exact chunk/vector coverage retain prior publications.
- Run-once cutoff, deferred backoff without spinning, supported configuration,
  owned-elsewhere exits, historical failures, startup recovery, bounded inference
  batches, heartbeat loss, interruption and credential/body-safe logs are covered.
- A real independent heartbeat renews a 1-second database lease while fake
  inference runs for 1.3 seconds.
- A restricted runtime role can admit, claim and publish; it cannot update model
  dimensions. Its documented `UPDATE(is_active)` grant is needed for `FOR SHARE`.

## Review and regressions

One fresh read-only reviewer examined the whole implementation. It identified
two important issues, both reproduced with failing tests and fixed:

1. The inherited character splitter removed significant boundary whitespace.
   Added an opt-in lossless mode for the worker; existing importer defaults stay
   unchanged. Space runs, indentation and Unicode-separator regressions pass.
2. Documented SELECT-only model permissions could not execute `FOR SHARE`.
   The guide now grants column-scoped `UPDATE(is_active)` and a real restricted-role
   integration test verifies admission/publication and denied identity edits.

Additional fault-injection regressions caught and fixed two lease boundary bugs:
completion is now fenced after publication writes, and failure/supersession
transitions repeat the token/live-lease predicate at the mutation. Slow database
work after an earlier ownership check cannot commit stale results/state.
All fixes passed the full suite. No reviewer minor findings were deferred.

## Implementation decisions and limits

- Work stayed in the authorized checkout on a feature branch so the user's
  uncommitted schema prerequisites remained available. Cost: filesystem isolation
  is shared; explicit staging preserved the user's unrelated files.
- Used direct Windows commands and a progress ledger instead of POSIX-only skill
  helper scripts. Cost: progress bookkeeping is maintained manually.
- Existing manifest Authentication maps to security; Performance maps to
  performance. Existing backend product labels and lowercase source types remain.
  Cost: these backend labels still need an explicit presentation mapping when a
  future retrieval UI consumes them.
- Optional encoder dependencies were resolved early with the PostgreSQL driver;
  Python >=3.14 remains unchanged. Cost: future platform/runtime compatibility
  still needs testing with the operator's selected hardware and pinned model.
- Runtime `UPDATE(is_active)` is column-scoped to satisfy PostgreSQL's lock
  permission rule without allowing model identity edits. Cost: that role can
  activate/deactivate registry entries; use a privileged locking function instead
  if operational policy forbids that status privilege.

No approved model identifier/revision/cache was supplied, so the real pinned-model
smoke was **not run**. The opt-in smoke is included and forces offline loading;
it verifies dimension/unit norm, unchanged admission without encoding, replacement
publication and forced rollback, then records Python/PyTorch/Sentence Transformers/
revision/OS/device. See `backend/docs/embedding-worker.md` for invocation.

No model downloads, production migrations, source fetches, scheduler installation,
push, merge or deployment occurred. Existing uncommitted SQL 001/002/003, SQL README,
database design and health-test changes were excluded from feature commits. The
additive migration depends on those reviewed schema prerequisites being applied
separately by the migration owner.
