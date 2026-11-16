# Support Copilot backend

## Incremental embedding worker

See [embedding worker setup and operations](docs/embedding-worker.md) for schema
prerequisites, pinned offline model configuration, explicit admission, run-once
processing, recovery and isolated integration tests. Imports remain staging-only;
the worker does not change the chat retrieval path or install a daily schedule.

## Prepare the demo knowledge dataset

The file-only ingestion command downloads a curated set of **official MongoDB
documentation** and prepares JSONL for a later database loader. It does not connect
to a database, generate embeddings, call an LLM, or change the chat endpoint.

From `backend/` in PowerShell:

```powershell
uv sync
uv run support-copilot-prepare-knowledge
```

Alternatively, use the installed Python environment directly:

```powershell
.venv/Scripts/python.exe -m support_copilot.knowledge.cli
```

The defaults resolve relative to the backend source location, so the module command
also works from another working directory. To rebuild prepared data from saved
downloads, with **no network access**:

```powershell
uv run support-copilot-prepare-knowledge --offline
```

Optional settings:

```powershell
uv run support-copilot-prepare-knowledge --manifest data/knowledge/sources.json --output data/knowledge/output --target-chars 2400 --delay 1
```

### Sources and scope

Review or edit `data/knowledge/sources.json` to choose the documents. The initial
16-page manifest covers:

- Atlas connection errors, DNS/TLS, IP access lists, drivers, and database users.
- MongoDB 8.0 connection strings/options, SCRAM authentication, and self-managed
  user authentication with `mongosh`.
- MongoDB 8.0 query analysis, explain results, compound/unique indexes, the ESR
  guideline, query optimization, and retryable writes.

Atlas pages are labeled `current-unversioned`; server references use explicit
`/docs/v8.0/` URLs and `version_scope: "8.0"`. Atlas feature availability still varies
by cluster tier. `deployment` metadata describes broad applicability; read the
source's feature-specific restrictions before recommending a setting.

Sources are fetched as publisher-provided Markdown using `?allTabs=true` to include
available driver/UI variants. This retains more context than a single default tab.
MongoDB documents its Markdown exports in its [documentation index](https://www.mongodb.com/docs/llms.txt).
The downloader checks [robots.txt](https://www.mongodb.com/robots.txt), identifies
itself, requests sequentially at one-second intervals, and retries transient errors
at most twice. Redirects remain within approved MongoDB Markdown documentation URLs.
There is no recursive crawling or HTML/browser fallback; unavailable sources are
reported for review.

The broad built-in roles reference was deliberately excluded: its published
Markdown omitted important role names during review. Atlas database-user guidance
remains in scope, but this corpus is not a complete role/privilege reference.

### Output files

Generated files live in `data/knowledge/output/` and are ignored by git:

| File | Contents |
| --- | --- |
| `documents.jsonl` | One normalized full document per line |
| `chunks.jsonl` | One searchable, citation-ready chunk per line |
| `report.json` | Per-source status, counts, failures, oversized chunks and manifest hash |
| `raw/doc_<id>.md` | Original decoded Markdown response, before normalization |
| `raw/doc_<id>.json` | Fetch URL, timestamp, HTTP metadata and raw content hash |

Each JSONL line is a standalone UTF-8 JSON object, with no enclosing array. Empty
exports mean there were no successful documents; inspect `report.json` before
importing. The command exits **0** on complete success, **1** on any source failure,
and **2** for invalid configuration. A partial run exports only successful sources
from that run; it never silently substitutes an older download. Old raw snapshots
remain available, but offline preparation reads only the current manifest.

Document records contain:

```text
schema_version, document_id, source_url, fetch_url, resolved_fetch_url,
title, product, deployment, version_scope, category, topics, source_type,
content_markdown, content_hash, fetched_at, raw_sha256
```

Chunk records contain:

```text
schema_version, chunk_id, document_id, document_content_hash, chunk_index,
source_url, fetch_url, title, product, deployment, version_scope, category,
topics, source_type, heading_path, text, char_count, oversized
```

`source_url` is the browser link for citations. `fetch_url` records the actual
requested Markdown variant. Documents retain fetch timestamps; chunks join back
to documents by `document_id` and `document_content_hash`.

### Import later

To import the full documents into the existing Docker Compose PostgreSQL service,
start PostgreSQL from the project root with `docker compose up -d postgres`. Then
run these commands from `backend/`:

```powershell
uv run support-copilot-import-documents --dry-run
uv run support-copilot-import-documents
```

Or use the module directly without refreshing console entry points:

```powershell
.venv/Scripts/python.exe -m support_copilot.knowledge.import_documents
```

The default input is `data/knowledge/output/documents.jsonl`; override it using
`--file <path>`. The importer validates all records before connecting, creates
`public.knowledge_documents(document_id TEXT PRIMARY KEY, data JSONB NOT NULL)`,
and upserts by `document_id` in one transaction. All document fields are retained
inside `data`. Repeating the same import updates existing documents without
duplicates. Documents absent from the input remain in the table. Existing chunks
and embeddings are left unchanged. The command requires Docker Compose and uses
the local service/database/user named in this project's `docker-compose.yaml`.

Verify from the project root:

```powershell
docker compose exec -T postgres psql -U support_copilot -d support_copilot -c "SELECT COUNT(*) FROM public.knowledge_documents;"
```

Expect 16 rows for a fresh table with the current dataset. Exit status is 0 for
success, 1 for Docker/database failure, and 2 for invalid or unreadable input.

1. Check that `report.json` has `failed: 0`, and inspect a sample of documents/chunks.
2. Load `documents.jsonl`, upserting by `document_id` (stable for a source URL).
3. Embed chunk `text` with your chosen model and load `chunks.jsonl`, preserving
   all metadata. Use `chunk_id` as the unique identifier.
4. Filter retrieval by product/deployment/version as appropriate and return
   `source_url`, `title`, and `heading_path` with each citation.
5. On reimport, replace the previous chunk set for each changed document rather
   than appending. Content or chunking changes produce new chunk IDs. Handle any
   sources removed from the manifest explicitly when refreshing your database.

Chunks split at headings and paragraphs, with heading context repeated and no
overlap. **2400 is a character target, not a token limit.** Fenced code and tables
remain whole; they may exceed this target and are marked `oversized`. Inspect them
against your embedding model's token limit before embedding; do not truncate code
silently. Markdown is source evidence, not executable instructions. The pipeline
removes export navigation/frontmatter but does not rewrite or verify the publisher's
technical claims or links.

### Demo checks

After adding retrieval, use questions such as these to inspect which chunks are
returned. These are manual retrieval checks, not a scored evaluation:

| Question | Relevant source/topic |
| --- | --- |
| Why does my Atlas connection time out? | Connection troubleshooting; IP access lists |
| Why does an SRV connection fail with a DNS error? | Connection troubleshooting; connection strings |
| Can my Atlas account password authenticate a database connection? | Database users; SCRAM |
| What does `authSource` mean? | Connection string options |
| Why does a query use COLLSCAN instead of IXSCAN? | Explain results; query analysis |
| What field order should I use in a compound index? | Compound indexes; ESR |
| Why am I getting E11000 duplicate-key errors? | Unique indexes |
| When can MongoDB retry a failed write? | Retryable writes |

Also ask an unsupported question (for example, your organization's refund policy)
and confirm the assistant states that the corpus has insufficient evidence.

### Tests

```powershell
uv run pytest -q
uv run ruff check src/support_copilot/knowledge tests/knowledge
```

Tests use a mocked HTTP transport and temporary files; they do not scrape live
documentation. Real downloads and offline reproducibility are verified separately.
