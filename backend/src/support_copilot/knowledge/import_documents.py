"""Import full knowledge documents into the configured PostgreSQL database."""

import argparse
import json
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from support_copilot.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_FILE = BACKEND_DIR / "data" / "knowledge" / "output" / "documents.jsonl"
REQUIRED_FIELDS = ("document_id", "title", "source_url", "content_markdown")


def _validate_strings(document: dict) -> None:
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                raise ValueError(
                    "JSONB strings cannot contain NUL or unpaired Unicode surrogates"
                )
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def load_documents(path: Path) -> list[dict]:
    """Validate every line before any database access; preserve all source fields."""
    documents = []
    seen = set()
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                document = json.loads(line)
                if not isinstance(document, dict) or any(
                    not isinstance(document.get(key), str) or not document[key].strip()
                    for key in REQUIRED_FIELDS
                ):
                    raise ValueError(
                        f"Expected a document with {', '.join(REQUIRED_FIELDS)}"
                    )
                if document["document_id"] in seen:
                    raise ValueError("Duplicate document_id")
                # PostgreSQL JSONB cannot represent non-finite JSON numbers.
                json.dumps(document, allow_nan=False)
                _validate_strings(document)
            except ValueError as exc:
                raise ValueError(f"Invalid document at line {number}: {exc}") from exc
            seen.add(document["document_id"])
            documents.append(document)
    if not documents:
        raise ValueError("The input file contains no documents")
    return documents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate without connecting"
    )
    args = parser.parse_args(argv)
    try:
        documents = load_documents(args.file)
    except (OSError, ValueError) as exc:
        print(f"Document import: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"Validated {len(documents)} documents; no database connection made.")
        return 0
    try:
        database_url = Settings().database_url.get_secret_value()
        if not database_url.strip():
            print("Set DATABASE_URL in backend/.env before importing.", file=sys.stderr)
            return 2
    except ValidationError:
        print("Invalid backend configuration; check backend/.env.", file=sys.stderr)
        return 2
    try:
        # The connection context commits the entire import, or rolls it back on error.
        with (
            psycopg.connect(database_url, connect_timeout=10) as conn,
            conn.cursor() as cursor,
        ):
            cursor.execute("""CREATE TABLE IF NOT EXISTS public.knowledge_documents (
                document_id TEXT PRIMARY KEY,
                data JSONB NOT NULL
            )""")
            cursor.executemany(
                """INSERT INTO public.knowledge_documents (document_id, data)
                VALUES (%s, %s)
                ON CONFLICT (document_id) DO UPDATE SET data = EXCLUDED.data""",
                [
                    (document["document_id"], Jsonb(document))
                    for document in documents
                ],
            )
    except (psycopg.Error, OSError):
        print(
            "Import failed; transaction not committed. Check DATABASE_URL, database connectivity and schema permissions.",
            file=sys.stderr,
        )
        return 1
    print(f"Imported {len(documents)} documents into public.knowledge_documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
