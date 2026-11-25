"""Finite PostgreSQL embedding worker; no polling or implicit admission."""

import argparse
import json
import logging
import signal
from dataclasses import asdict, dataclass
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic

import psycopg
from pydantic import ValidationError

from support_copilot.application.use_cases.process_embedding_job import process_job
from support_copilot.domain.embedding_job import OwnershipLost, ProcessingError
from support_copilot.interface.worker.heartbeat import Heartbeat

logger = logging.getLogger(__name__)


@dataclass
class WorkerSummary:
    completed: int = 0
    superseded: int = 0
    failed: int = 0
    recovered: int = 0
    deferred: int = 0
    blocked: int = 0
    owned_elsewhere: int = 0
    rescheduled: int = 0
    ownership_lost: int = 0
    interrupted: bool = False

    @property
    def exit_code(self):
        return int(
            bool(
                self.failed
                or self.blocked
                or self.rescheduled
                or self.ownership_lost
                or self.interrupted
            )
        )


def run_once(
    store,
    encoder_factory,
    chunker,
    config,
    stop: Event,
    *,
    heartbeat_seconds=60,
    batch_size=32,
):
    if heartbeat_seconds <= 0 or batch_size <= 0:
        raise ValueError("Heartbeat and batch size must be positive")
    store.validate_configuration(config)
    cutoff = store.now()
    recovery = store.recover(cutoff)
    summary = WorkerSummary(
        recovered=recovery.recovered,
        failed=recovery.failed,
        superseded=recovery.superseded,
    )
    encoder = None
    while not stop.is_set():
        job = store.claim(config.config_hash, cutoff)
        if job is None:
            break
        started = monotonic()
        try:
            if not store.is_current(job):
                summary.superseded += 1
                continue
            with Heartbeat(store, job, heartbeat_seconds) as heartbeat:
                results = Queue(maxsize=1)

                def execute(job=job, results=results, heartbeat=heartbeat):
                    nonlocal encoder
                    try:
                        if encoder is None:
                            encoder = encoder_factory()
                        result = process_job(
                            store,
                            job,
                            chunker,
                            encoder,
                            lambda: stop.is_set() or heartbeat.lost.is_set(),
                            batch_size=batch_size,
                        )
                        results.put((result, None))
                    except Exception as processing_error:  # noqa: BLE001 -- propagated privately, never logged verbatim
                        results.put((None, processing_error))

                inference = Thread(target=execute, daemon=True, name="embedding-job")
                inference.start()
                while True:
                    if stop.is_set():
                        summary.interrupted = True
                        break
                    if heartbeat.lost.is_set():
                        raise OwnershipLost()
                    try:
                        status, error = results.get(timeout=0.05)
                        break
                    except Empty:
                        continue
                if summary.interrupted:
                    # Daemon inference observes stop before any eventual publication.
                    # Keep claim recoverable; do not mutate an unfinished job.
                    break
                if heartbeat.lost.is_set():
                    raise OwnershipLost()
                if error is not None:
                    raise error
                if status == "completed":
                    summary.completed += 1
                else:
                    summary.superseded += 1
                logger.info(
                    json.dumps(
                        {
                            "event": status,
                            "job_id": str(job.id),
                            "document_id": job.document_id,
                            "revision_id": str(job.revision_id),
                            "generation": job.generation,
                            "config_hash": config.config_hash,
                            "attempt": job.attempts,
                            "duration_seconds": round(monotonic() - started, 3),
                        }
                    )
                )
        except OwnershipLost:
            summary.ownership_lost += 1
            break  # don't reuse an encoder still busy in a daemon thread
        except Exception as error:  # noqa: BLE001 -- classify safely at the process boundary
            code, retryable = "encoding_failed", False
            if isinstance(error, ProcessingError):
                code, retryable = error.code, error.retryable
            elif isinstance(
                error,
                (
                    psycopg.OperationalError,
                    psycopg.InterfaceError,
                    psycopg.errors.TransactionRollback,
                    MemoryError,
                ),
            ):
                code, retryable = (
                    "database_unavailable"
                    if isinstance(error, psycopg.Error)
                    else "encoding_resource",
                    True,
                )
            try:
                status = store.fail(job, code, retryable)
            except (OwnershipLost, psycopg.Error):
                summary.ownership_lost += 1
                break
            if status == "pending":
                summary.rescheduled += 1
            elif status == "superseded":
                summary.superseded += 1
            else:
                summary.failed += 1
            # Only application-owned codes, never raw exception messages.
            logger.warning(
                json.dumps(
                    {
                        "event": status,
                        "job_id": str(job.id),
                        "error_code": code
                        if code
                        in {
                            "encoding_resource",
                            "database_unavailable",
                            "model_unavailable",
                            "interrupted",
                        }
                        else "processing_error",
                    }
                )
            )
            if code in {
                "model_unavailable",
                "model_dimension_mismatch",
                "tokenizer_limit_mismatch",
            }:
                break
    observation = store.observe(config.config_hash, cutoff)
    summary.blocked = observation.blocked
    summary.deferred = observation.deferred
    summary.owned_elsewhere = observation.owned_elsewhere
    summary.interrupted = summary.interrupted or stop.is_set()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    stop = Event()
    previous = {}
    try:
        from support_copilot.bootstrap import build_embedding_worker

        store, encoder_factory, chunker, settings = build_embedding_worker()
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: stop.set())
        summary = run_once(
            store,
            encoder_factory,
            chunker,
            settings.effective_config(),
            stop,
            heartbeat_seconds=settings.heartbeat_seconds,
            batch_size=settings.batch_size,
        )
        print(json.dumps({**asdict(summary), "exit_code": summary.exit_code}))
        return summary.exit_code
    except (ValidationError, ValueError):
        print(json.dumps({"error": "invalid_configuration"}))
        return 2
    except (ProcessingError, psycopg.Error, OSError):
        print(json.dumps({"error": "worker_startup_or_database_failure"}))
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
