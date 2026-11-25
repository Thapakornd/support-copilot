# Support Copilot backend

## Environment variables

Install Python 3.14+ and uv. If `backend/.env` is missing, copy
[`.env.example`](.env.example) to `backend/.env`. Uncomment the settings you need
and replace the placeholders. Backend commands load this file from its absolute
path. Process environment variables take precedence over values in the file.

### Minimum configuration by command

| What you want to run | What to set |
| --- | --- |
| `support-copilot` for `/health` and `/docs` | No required variables. Keep the template's `CORS_ORIGINS` for the local Vite frontend. |
| `support-copilot` for `/chat` | `DATABASE_URL`, the [embedding model settings](#required-embedding-model-settings) used to publish the corpus, `LLM_MODEL`, and the key for the selected provider. Install the embeddings extra. |
| `support-copilot-prepare-knowledge` or `support-copilot-import-documents --dry-run` | No required variables. |
| `support-copilot-import-documents` | `DATABASE_URL`. |
| `support-copilot-enqueue-embeddings` and `support-copilot-worker` | One PostgreSQL connection (`DATABASE_URL` or `EMBEDDING_DATABASE_URL`) and the seven [required embedding model settings](#required-embedding-model-settings). |

### Database, API, and chat settings

| Variable | Required or default | What to set |
| --- | --- | --- |
| `DATABASE_URL` | Required for imports and shared by the embedding commands by default. | PostgreSQL connection URI. The template points to the local Compose database. Use the URI for your own database when deploying. Percent-encode special characters in URI credentials. |
| `EMBEDDING_DATABASE_URL` | Optional override. Falls back to `DATABASE_URL` for enqueue and worker commands. | Set a PostgreSQL URI here if embeddings use a different runtime role or connection endpoint. The importer still uses `DATABASE_URL`. Use the same database for both when embedding imported documents. |
| `API_HOST` | Optional, `127.0.0.1`. | Address the API binds to. Use `127.0.0.1` for local development or `0.0.0.0` when the API needs to listen on all IPv4 interfaces. |
| `API_PORT` | Optional, `8000`. | API listening port from `1` to `65535`. The frontend API URL must use this port. |
| `API_RELOAD` | Optional, `false`. The local template sets `true`. | Use `true` to restart the API when code changes during development. |
| `CORS_ORIGINS` | Optional, `[]`. The local template allows `http://localhost:5173`. | JSON array of browser frontend origins, including scheme and port if applicable. For example, `["http://localhost:5173"]`. Use the exact hostname the browser opens. |
| `DEMO_AUTH` | Optional, `false`. | Set `true` to let the `X-Demo-User: <subject>` header sign requests in as a user with `auth_issuer='demo'` (frontend endpoints only; `/chat` and `/health` are unaffected). The header is impersonation by design, so settings reject `true` unless `API_HOST` is `127.0.0.1`, `localhost` or `::1`. With `false`, every frontend endpoint returns 401. Seed the demo people with `backend/sql/demo_identities.sql`. |
| `LLM_PROVIDER` | Optional, `anthropic`. | Use `anthropic` for direct Anthropic access or `openrouter` for OpenRouter. |
| `LLM_MODEL` | Required for `/chat`. | Set the exact model ID available to your provider account. |
| `ANTHROPIC_API_KEY` | Required for Anthropic chat. | Set the API key from your Anthropic account. Keep it in your local `.env` or environment. |
| `OPENROUTER_API_KEY` | Required for OpenRouter chat. | Set your OpenRouter key in the backend environment or local `.env`. Set `LLM_MODEL` to the full OpenRouter model ID and select a model that supports tool calling for structured answers. |

### Required embedding model settings

Use the same values for enqueue and worker commands. Register the model in
`public.embedding_models` and apply the schema for its dimensions before running
either command. The [embedding worker guide](docs/embedding-worker.md) covers the
registry, permissions, migrations, and first run.

| Variable | What to set |
| --- | --- |
| `EMBEDDING_MODEL_ID` | UUID of the active row in `public.embedding_models` for this model and revision. Generate a UUID when registering a new model and reuse it here. |
| `EMBEDDING_MODEL_NAME` | Exact Hugging Face model identifier recorded in `model_name`, for example `intfloat/e5-small-v2`. |
| `EMBEDDING_MODEL_REVISION` | Full 40-character lowercase Git commit SHA from the model repository, matching `model_revision` in PostgreSQL. Use the SHA for the files you intend to load. |
| `EMBEDDING_DIMENSIONS` | Number of floats the model outputs per embedding. Match the model, registry row, and `vector(N)` column created by `002_embeddings.sql`. |
| `EMBEDDING_TOKENIZER_LIMIT` | Positive maximum input length in tokens, including the prefix and special tokens. Use the model's supported tokenizer limit or a lower value. |
| `EMBEDDING_DOCUMENT_PROMPT` | Prefix the model expects for document passages. Use `""` if it needs an empty prefix. Preserve any trailing space specified by the model. |
| `EMBEDDING_QUERY_PROMPT` | Prefix the model expects for search queries. Use `""` if it needs an empty prefix. Keep it identical across chat and publication. |

For example, the [E5-small-v2 model card](https://huggingface.co/intfloat/e5-small-v2)
specifies `384` dimensions, a `512`-token input limit, and the prefixes
`"passage: "` and `"query: "`. Use your registered UUID and the commit SHA for the
revision you selected. Both prompt variables must be explicitly set.

### Optional embedding settings

| Variable | Default | What it controls |
| --- | --- | --- |
| `EMBEDDING_OFFLINE` | `true` | Load the pinned model from the local cache. Set `false` to allow the first download if the files are missing. |
| `EMBEDDING_DEVICE` | `cpu` | Device used for model inference. Keep `cpu` for CPU-only development or set a device supported by your installed runtime, such as `cuda` on a compatible setup. |
| `EMBEDDING_LEASE_SECONDS` | `300` | How long a worker owns a claimed job before another run can recover the expired claim. Set a positive duration longer than the heartbeat interval. |
| `EMBEDDING_HEARTBEAT_SECONDS` | `60` | How often the worker renews its claim. Set a positive interval shorter than the lease. |
| `EMBEDDING_MAX_ATTEMPTS` | `3` | Maximum processing attempts recorded when a job is enqueued, including its first attempt. Use a positive integer. |
| `EMBEDDING_BATCH_SIZE` | `32` | Maximum passages encoded per inference batch. Use a positive integer. Lower it if inference runs out of memory. |
| `EMBEDDING_MAX_DOCUMENT_TOKENS` | `100000` | Positive token budget for each document and its prepared chunks. Exceeding the budget fails the job. |
| `EMBEDDING_MAX_DOCUMENT_CHUNKS` | `2000` | Positive maximum number of chunks per document. Exceeding it fails the job. |
| `EMBEDDING_TARGET_CHARS` | `2400` | Initial target chunk size in characters, with a minimum of `100`. The worker also checks the actual token limit. |

## API startup

For local development only, optionally start the separate Compose database from
the project root:

```powershell
docker compose up -d postgres
```

Compose has its own local database configuration in `docker-compose.yaml` and
does not consume `backend/.env`. The example `DATABASE_URL` connects to this local
database; replace it with your external database connection string when deploying.
Schema migrations remain manual; see [SQL setup](sql/README.md).

From `backend/`, start the API:

```powershell
uv sync --extra embeddings
uv run --extra embeddings support-copilot
```

With the example port, health is at `http://127.0.0.1:8000/health` and interactive
API documentation at `http://127.0.0.1:8000/docs`. Health/docs work without an LLM
or database. For `/chat`, grant the API role schema usage and SELECT on
`categories`, `embedding_models`, `knowledge_documents`, `knowledge_document_revisions`,
`knowledge_chunk_sets`, `knowledge_revision_chunks`, `chunk_embeddings`, and
`retrieval_publications`. Point `DATABASE_URL` at the database with the published
corpus. Match the publishing worker's model, prompts, tokenizer limit,
`EMBEDDING_TARGET_CHARS`, `EMBEDDING_MAX_DOCUMENT_TOKENS` and
`EMBEDDING_MAX_DOCUMENT_CHUNKS`. Retrieval checks the full chunk-set configuration
hash before ranking candidates. See the [RAG chat workflow](docs/rag-chat.md) for the publication check
and the request and response contract.

## Chat retrieval settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `CHAT_CANDIDATE_LIMIT` | 20 | Maximum nearest passages fetched for one question. |
| `CHAT_MAX_DISTANCE` | 0.5 | Largest cosine distance accepted. Calibrate this cutoff using questions from your corpus. |
| `CHAT_MAX_PASSAGES` | 6 | Maximum passages sent to the generation model. |
| `CHAT_EVIDENCE_CHAR_LIMIT` | 12000 | Evidence character budget. Select a value that fits your generation model alongside the question, instructions and output. |
| `LLM_TIMEOUT_SECONDS` | 30 | Timeout passed to the generation provider. |

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

### Third-party content and licensing

This is a personal, non-commercial learning project. It is not affiliated with,
endorsed by or sponsored by MongoDB, Inc. "MongoDB" and "Atlas" are trademarks of
MongoDB, Inc.

- **No MongoDB text is stored in this repository.** `data/knowledge/sources.json`
  lists URLs only. The downloaded and prepared documentation (`data/knowledge/output/`)
  and the database contents are generated on your machine and are gitignored. Do not
  commit or redistribute them.
- **The documentation belongs to MongoDB.** The
  [mongodb/docs repository](https://github.com/mongodb/docs) states that the
  documentation is under
  [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/), while the
  [website terms of use](https://www.mongodb.com/legal/terms-of-use) limit copying to
  personal, educational and non-commercial use and restrict automated retrieval.
  These sources do not fully agree, so read both before running the downloader.
- **Keep your use personal, educational and non-commercial.** Keep the attribution
  shown with each answer's cited sources. For any public or commercial deployment,
  get written permission from MongoDB or replace the corpus with content you own or
  that is licensed for it.

This section is a good-faith note, not legal advice.

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
and embeddings are left unchanged. The importer connects directly using `DATABASE_URL` from `backend/.env` or the
process environment. Docker is only needed if you choose the local Compose database.

Verify from the project root:

```powershell
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT COUNT(*) FROM public.knowledge_documents;"'
```

Expect 16 rows for a fresh table with the current dataset. Exit status is 0 for
success, 1 for database failure, and 2 for invalid configuration or unreadable input.

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
