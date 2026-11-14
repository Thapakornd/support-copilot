"""Import full knowledge documents through the project's Docker PostgreSQL service."""

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
PROJECT_DIR = BACKEND_DIR.parent
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


def build_sql(documents: list[dict]) -> str:
    """CSV-encode JSON to preserve quotes, backslashes and Unicode through COPY."""
    data = io.StringIO(newline="")
    writer = csv.writer(data, lineterminator="\n")
    for document in documents:
        writer.writerow([json.dumps(document, ensure_ascii=True, allow_nan=False)])
    return (
        """BEGIN;
CREATE TABLE IF NOT EXISTS public.knowledge_documents (
    document_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);
CREATE TEMP TABLE incoming_knowledge_documents (data JSONB NOT NULL) ON COMMIT DROP;
COPY incoming_knowledge_documents(data) FROM STDIN WITH (FORMAT csv);
"""
        + data.getvalue()
        + """\\.
INSERT INTO public.knowledge_documents (document_id, data)
SELECT data->>'document_id', data FROM incoming_knowledge_documents
ON CONFLICT (document_id) DO UPDATE SET data = EXCLUDED.data;
SELECT COUNT(*) AS documents_in_table FROM public.knowledge_documents;
COMMIT;
"""
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate without connecting"
    )
    args = parser.parse_args(argv)
    try:
        documents = load_documents(args.file)
        sql = build_sql(documents)
    except (OSError, ValueError) as exc:
        print(f"Document import: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"Validated {len(documents)} documents; no database connection made.")
        return 0
    command = [
        "docker",
        "compose",
        "--file",
        str(PROJECT_DIR / "docker-compose.yaml"),
        "exec",
        "-T",
        "postgres",
        "psql",
        "-X",
        "--username",
        "support_copilot",
        "--dbname",
        "support_copilot",
        "--set",
        "ON_ERROR_STOP=1",
    ]
    try:
        result = subprocess.run(
            command, input=sql, encoding="utf-8", cwd=PROJECT_DIR, check=False
        )
    except OSError:
        print(
            "Could not start Docker. Ensure Docker is installed and running.",
            file=sys.stderr,
        )
        return 1
    if result.returncode:
        print(
            "Import failed. The transaction was not committed. Check the psql/Docker error above.",
            file=sys.stderr,
        )
        return 1
    print(f"Imported {len(documents)} documents into public.knowledge_documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
