# Knowledge Preparation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a working MongoDB documentation scraper and prepared file dataset for later database import.

**Architecture:** A fixed JSON manifest drives a polite HTTPX downloader. Pure Markdown preparation generates database-neutral documents and citation chunks. A CLI coordinates snapshots, JSONL exports, and a report; offline mode reuses snapshots.

**Tech Stack:** Python 3.14, HTTPX, pytest, standard-library JSON/hashlib/urllib.robotparser.

**Spec:** docs/superpowers/specs/2026-11-14-knowledge-preparation-design.md

## Global Constraints

- No database writes, embeddings, paid APIs, or chat behavior changes.
- Curated official MongoDB docs only; metadata explicitly distinguishes current/unversioned scopes.
- UTF-8 JSONL, stable IDs, source URLs and per-run failure reporting.
- Preserve code blocks and report blocks beyond the character target.

## Review Focus

- Off-host/path redirects must fail before the redirected request.
- Headings inside code fences must not split sections.
- Failed sources or stale snapshots must not silently enter fresh output.
- Offline preparation must not access the network.
- A blocked or invalid robots response must not permit a download.

### Task 1: Markdown preparation

Files: src/support_copilot/knowledge/prepare.py, tests/knowledge/test_prepare.py (under backend).
Interfaces: prepare_document(source, markdown, fetched_at) -> dict; chunk_document(document, target_chars=2400) -> list[dict].
- [x] Write tests for title/frontmatter, code preservation, heading paths, oversized blocks, stable IDs, version metadata, empty/HTML rejection.
- [x] Run focused tests and confirm missing behavior.
- [x] Implement normalization and deterministic heading-aware chunking.
- [x] Run focused tests and Ruff.

### Task 2: Downloader and CLI

Files: knowledge/download.py, knowledge/cli.py, data/knowledge/sources.json, tests/knowledge/test_pipeline.py; update pyproject.toml/uv.lock.
Interfaces: run_pipeline(manifest_path, output_dir, offline=False, client=None, delay=1.0) -> report; CLI returns nonzero for any failed source.
- [x] Write tests using HTTPX MockTransport for retries, redirects, robots, snapshots, partial failures and offline reproducibility.
- [x] Confirm failures, then implement downloader and CLI.
- [x] Validate the manifest (required fields, unique source URLs) before making requests.
- [x] Add console entry point, runtime HTTPX dependency, gitignore rules and run tests.

### Task 3: Produce and verify the demo dataset

Files: backend/README.md; generated backend/data/knowledge/output/.
- [x] Download selected real pages, fix invalid source choices using official documentation indexes, and record all failures.
- [x] Inspect normalized documents and chunks, counts, fence/heading preservation and topic coverage.
- [x] Verify offline rerun yields identical documents/chunks and run full backend suite plus Ruff.
- [x] Request a fresh code review, address material findings, document commands/schema and report limitations.

## Execution notes

The repository has no initial commit and all existing application files are untracked. Work in the supplied workspace and leave existing files in place; creating an initial commit or an empty worktree would sweep in unrelated user work or omit the current project. No commit or branch integration is part of this request.


## Verification record

- Final live run: 16 documents, 348 chunks, zero failed sources.
- Offline rebuild: documents.jsonl and chunks.jsonl byte-for-byte identical.
- Corpus QA: unique IDs, valid document/chunk joins and hashes, correct character
  counts, and all 216 fenced code blocks preserved through normalization/chunking.
- Eight indivisible code/table chunks exceed the 2400-character target; largest
  is 8547 characters. These are explicitly marked oversized for import-time review.
- Final backend suite: 34 passed. Ruff lint and format checks passed for new code.
- Existing LangSmith dependency emits 13 Python deprecation warnings.
- Fresh review found CRLF checksum and list-heading scope issues. Both reproduced
  in failing regression tests, then fixed; final suite is green.
- Source curation replaced a built-in roles reference with the focused self-managed
  authentication tutorial because its publisher Markdown omitted role names.
- Initial health test hang came from sandbox-local socket creation. The unchanged
  health test passes outside that restriction; no unrelated application fix made.
- No database, embedding, git commit, push, or branch integration was performed.
