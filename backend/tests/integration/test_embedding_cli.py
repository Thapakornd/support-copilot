import json
import os
import subprocess
import sys
from pathlib import Path

from test_embedding_admission import stage

from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)


def command(db, config, module, *args, **changes):
    env = {
        **os.environ,
        "EMBEDDING_DATABASE_URL": db,
        "EMBEDDING_MODEL_ID": str(config.model_id),
        "EMBEDDING_MODEL_NAME": config.model_name,
        "EMBEDDING_MODEL_REVISION": config.model_revision,
        "EMBEDDING_DIMENSIONS": str(config.dimensions),
        "EMBEDDING_TOKENIZER_LIMIT": str(config.tokenizer_limit),
        "EMBEDDING_DOCUMENT_PROMPT": config.document_prompt,
        "EMBEDDING_QUERY_PROMPT": config.query_prompt,
        "EMBEDDING_OFFLINE": "true",
        **changes,
    }
    result = subprocess.run(
        [sys.executable, "-m", "support_copilot.interface.worker." + module, *args],
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_real_cli_admission_no_work_blocked_configuration_and_retry(db, config):
    code, summary = command(db, config, "main", "--once")
    assert code == 0 and summary["completed"] == 0
    stage(db)
    code, summary = command(db, config, "enqueue", "--all")
    assert code == 0 and summary == {"admitted": 1, "unchanged": 0, "rejected": 0}
    code, summary = command(db, config, "enqueue", "--document-id", "doc-1")
    assert code == 0 and summary["unchanged"] == 1
    code, summary = command(
        db, config, "main", "--once", EMBEDDING_DOCUMENT_PROMPT="different: "
    )
    assert code == 1 and summary["blocked"] == 1
    store = KnowledgeRepository(db)
    job = store.claim(config.config_hash, store.now())
    store.fail(job, "invalid_source", False)
    code, summary = command(db, config, "enqueue", "--retry-job", str(job.id))
    assert code == 0 and summary == {"retried": 1}
    assert store.claim(config.config_hash, store.now()).attempts == 1


def test_real_cli_atomic_batch_rejection(db, config):
    stage(db, category="unknown")
    code, summary = command(db, config, "enqueue", "--all")
    assert code == 1 and summary["admitted"] == 0 and summary["rejected"] == 1
