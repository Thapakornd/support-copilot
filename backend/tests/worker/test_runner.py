from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest
from support_copilot.domain.embedding_job import (
    EmbeddingConfig,
    EmbeddingJob,
    ProcessingError,
    QueueObservation,
    RecoveryResult,
)
from support_copilot.interface.worker.main import run_once


class Store:
    def __init__(self, count=0):
        self.config = EmbeddingConfig(
            uuid4(), "approved/test", "a" * 40, 3, 128, "", ""
        )
        self.jobs = [
            EmbeddingJob(uuid4(), str(i), uuid4(), 1, self.config, 1, uuid4())
            for i in range(count)
        ]
        self.published = []
        self.failures = []
        self.recovery = RecoveryResult()
        self.observation = QueueObservation()
        self.current = True
        self.cutoff = datetime(2026, 11, 16, tzinfo=UTC)

    def validate_configuration(self, config):
        assert config == self.config

    def now(self):
        return self.cutoff

    def recover(self, cutoff):
        assert cutoff == self.cutoff
        return self.recovery

    def claim(self, config_hash, cutoff):
        assert cutoff == self.cutoff and config_hash == self.config.config_hash
        return self.jobs.pop(0) if self.jobs else None

    def observe(self, config_hash, cutoff):
        return self.observation

    def is_current(self, job):
        return self.current

    def renew(self, job):
        return True

    def load_snapshot(self, job):
        return {}

    def publish(self, job, chunks, vectors):
        self.published.append((job.id, chunks, vectors))
        return "completed"

    def fail(self, job, code, retryable):
        self.failures.append((job.id, code, retryable))
        return "pending" if retryable else "failed"


class Chunker:
    def chunks(self, snapshot, config, encoder):
        return [{"text": "first"}, {"text": "second"}, {"text": "third"}]


class Encoder:
    def __init__(self):
        self.batches = []

    def encode_documents(self, texts):
        self.batches.append(texts)
        return [[1, 0, 0] for _ in texts]


def test_no_work_or_superseded_never_loads_model():
    for count in [0, 2]:
        store = Store(count)
        store.current = False

        def unexpected():
            pytest.fail("Model loaded without useful encoding work")

        summary = run_once(store, unexpected, Chunker(), store.config, Event())
        assert summary.exit_code == 0
        assert summary.superseded == count


def test_single_model_reused_bounded_batches_and_cutoff():
    store = Store(2)
    encoders = []

    def factory():
        encoders.append(Encoder())
        return encoders[-1]

    summary = run_once(store, factory, Chunker(), store.config, Event(), batch_size=2)
    assert summary.completed == 2 and summary.exit_code == 0
    assert len(encoders) == 1
    assert encoders[0].batches == [
        ["first", "second"],
        ["third"],
        ["first", "second"],
        ["third"],
    ]
    assert len(store.published) == 2


@pytest.mark.parametrize(
    "observation,expected",
    [
        (QueueObservation(owned_elsewhere=2), 0),
        (QueueObservation(deferred=2), 0),
        (QueueObservation(blocked=2), 1),
    ],
)
def test_observed_queue_exit_contract(observation, expected):
    store = Store()
    store.observation = observation
    assert (
        run_once(store, Encoder, Chunker(), store.config, Event()).exit_code == expected
    )


def test_exhausted_recovery_fails_invocation():
    store = Store()
    store.recovery = RecoveryResult(recovered=2, failed=1)
    summary = run_once(store, Encoder, Chunker(), store.config, Event())
    assert summary.recovered == 2 and summary.failed == 1 and summary.exit_code == 1


def test_encoding_resource_failure_is_deferred_and_sanitized(caplog):
    store = Store(1)

    class Broken(Encoder):
        def encode_documents(self, texts):
            raise ProcessingError("encoding_resource", retryable=True)

    summary = run_once(store, Broken, Chunker(), store.config, Event())
    assert summary.rescheduled == 1 and summary.exit_code == 1
    assert not store.published
    assert store.failures[0][1:] == ("encoding_resource", True)


def test_heartbeat_loss_prevents_publication():
    store = Store(1)
    ownership_checked = Event()

    def lost(job):
        ownership_checked.set()
        return False

    store.renew = lost

    class Blocking(Encoder):
        def encode_documents(self, texts):
            assert ownership_checked.wait(2)
            return super().encode_documents(texts)

    summary = run_once(
        store, Blocking, Chunker(), store.config, Event(), heartbeat_seconds=0.01
    )
    assert summary.exit_code == 1 and summary.ownership_lost == 1
    assert not store.published and not store.failures


def test_interruption_is_bounded_and_never_completes_partial_job():
    store = Store(1)
    stop = Event()

    class Interrupted(Encoder):
        def encode_documents(self, texts):
            stop.set()
            return super().encode_documents(texts)

    summary = run_once(store, Interrupted, Chunker(), store.config, stop)
    assert summary.interrupted and summary.exit_code == 1
    assert not store.published


def test_arbitrary_error_does_not_log_secrets(caplog):
    store = Store(1)

    class Broken(Encoder):
        def encode_documents(self, texts):
            raise ValueError("secret-password and document-body")

    summary = run_once(store, Broken, Chunker(), store.config, Event())
    assert summary.failed == 1
    assert "secret-password" not in caplog.text and "document-body" not in caplog.text
    assert store.failures[0][1] == "encoding_failed"
