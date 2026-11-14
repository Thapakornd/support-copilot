"""Download a curated corpus or rebuild database-neutral exports offline."""

import argparse
import json
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import httpx

from support_copilot.knowledge.download import Downloader, validate_url
from support_copilot.knowledge.prepare import chunk_document, digest, prepare_document

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge"
REQUIRED = (
    "source_url",
    "fetch_url",
    "product",
    "deployment",
    "version_scope",
    "category",
)


def load_manifest(path: Path) -> list[dict]:
    sources = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sources, list) or not sources:
        raise ValueError("Manifest must contain a nonempty list of sources")
    seen = set()
    fetches = set()
    for source in sources:
        if not isinstance(source, dict) or any(
            not isinstance(source.get(key), str) or not source[key].strip()
            for key in REQUIRED
        ):
            raise ValueError(
                f"Each source requires nonempty fields: {', '.join(REQUIRED)}"
            )
        validate_url(source["fetch_url"])
        validate_url(source["source_url"].rstrip("/") + ".md")
        if source["source_url"] in seen or source["fetch_url"] in fetches:
            raise ValueError("Manifest contains duplicate source or fetch URLs")
        if (
            not isinstance(source.get("topics"), list)
            or not source["topics"]
            or any(not isinstance(t, str) or not t.strip() for t in source["topics"])
        ):
            raise ValueError("Each source requires a nonempty list of topic strings")
        seen.add(source["source_url"])
        fetches.add(source["fetch_url"])
    return sources


def _write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    temporary.replace(path)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _jsonl(records: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)


def run_pipeline(
    manifest_path: Path,
    output_dir: Path,
    *,
    offline: bool = False,
    client: httpx.Client | None = None,
    delay: float = 1.0,
    target_chars: int = 2400,
) -> dict:
    sources = load_manifest(manifest_path)
    if delay < 0 or target_chars < 100:
        raise ValueError("delay must be nonnegative and target_chars at least 100")
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    documents, chunks, results = [], [], []
    context = nullcontext(client) if client is not None or offline else httpx.Client()
    with context as http:
        downloader = Downloader(http, delay=delay) if not offline else None
        for source in sources:
            key = "doc_" + digest(source["source_url"])[:24]
            raw_path = raw_dir / (key + ".md")
            meta_path = raw_dir / (key + ".json")
            try:
                if offline:
                    snapshot = json.loads(meta_path.read_text(encoding="utf-8"))
                    if any(
                        snapshot[k] != source[k] for k in ("source_url", "fetch_url")
                    ):
                        raise ValueError(
                            "Snapshot URL differs from manifest; download it again"
                        )
                    # Preserve original line endings for the raw-response hash.
                    markdown = raw_path.read_bytes().decode("utf-8")
                    if digest(markdown) != snapshot["raw_sha256"]:
                        raise ValueError("Snapshot content hash mismatch")
                else:
                    snapshot = downloader.fetch(source["fetch_url"])
                    markdown = snapshot.pop("markdown")
                    snapshot.update({k: source[k] for k in ("source_url", "fetch_url")})
                    _write(raw_path, markdown)
                    _write(meta_path, _json(snapshot))
                document = prepare_document(source, markdown, snapshot["fetched_at"])
                document["resolved_fetch_url"] = snapshot["resolved_fetch_url"]
                document["raw_sha256"] = snapshot["raw_sha256"]
                prepared_chunks = chunk_document(document, target_chars)
                if not prepared_chunks:
                    raise ValueError("Document produced no usable chunks")
                documents.append(document)
                chunks.extend(prepared_chunks)
                results.append(
                    {
                        "source_url": source["source_url"],
                        "status": "ok",
                        "document_id": key,
                        "title": document["title"],
                        "chunk_count": len(prepared_chunks),
                        "content_chars": len(document["content_markdown"]),
                        "resolved_fetch_url": snapshot["resolved_fetch_url"],
                    }
                )
                print(
                    f"OK {document['title']}: {len(prepared_chunks)} chunks", flush=True
                )
            except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
                results.append(
                    {
                        "source_url": source["source_url"],
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"FAILED {source['source_url']}: {exc}", flush=True)

    report = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "offline" if offline else "download",
        "manifest_sha256": digest(_json(sources)),
        "requested": len(sources),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "failed": len(sources) - len(documents),
        "target_chars": target_chars,
        "chunking": "heading-aware; no overlap; fences/tables kept whole",
        "oversized_chunk_count": sum(chunk["oversized"] for chunk in chunks),
        "sources": results,
    }
    # Replace exports, rather than append: stale sources cannot enter this run.
    _write(output_dir / "documents.jsonl", _jsonl(documents))
    _write(output_dir / "chunks.jsonl", _jsonl(chunks))
    _write(output_dir / "report.json", _json(report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "sources.json")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "output")
    parser.add_argument(
        "--offline", action="store_true", help="Re-prepare cached downloads only"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Seconds between requests"
    )
    parser.add_argument("--target-chars", type=int, default=2400)
    args = parser.parse_args(argv)
    try:
        report = run_pipeline(
            args.manifest,
            args.output,
            offline=args.offline,
            delay=args.delay,
            target_chars=args.target_chars,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"knowledge preparation: {exc}\n")
    print(
        f"Prepared {report['document_count']} documents / {report['chunk_count']} chunks; "
        f"{report['failed']} failed. Output: {args.output.resolve()}"
    )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
