"""Explicit staging admission and current failed-job retry."""

import argparse
import json
import logging
from dataclasses import asdict
from uuid import UUID

import psycopg
from pydantic import ValidationError
from support_copilot.application.use_cases.enqueue_embedding import (
    AdmissionError,
    enqueue,
    retry_failed,
)
from support_copilot.domain.embedding_job import ProcessingError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group(required=True)
    select.add_argument("--all", action="store_true")
    select.add_argument("--document-id", action="append")
    select.add_argument("--retry-job", type=UUID)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        from support_copilot.bootstrap import build_embedding_admission

        store, config = build_embedding_admission()
        if args.retry_job:
            retry_failed(store, args.retry_job)
            print(json.dumps({"retried": 1}))
        else:
            print(json.dumps(asdict(enqueue(store, config, args.document_id))))
        return 0
    except (ValidationError, ValueError):
        print(json.dumps({"error": "invalid_configuration"}))
        return 2
    except AdmissionError as error:
        print(
            json.dumps(
                {
                    "admitted": 0,
                    "unchanged": 0,
                    "rejected": error.rejected,
                    "error": "invalid_source",
                }
            )
        )
        return 1
    except ProcessingError:
        print(json.dumps({"error": "admission_rejected"}))
        return 1
    except (psycopg.Error, OSError):
        print(json.dumps({"error": "database_or_schema_unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
