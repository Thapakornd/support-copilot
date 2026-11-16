import pytest
from pydantic import ValidationError
from support_copilot.core.config import WorkerSettings
from support_copilot.interface.worker.enqueue import main as enqueue_main
from support_copilot.interface.worker.main import main as worker_main


@pytest.mark.parametrize(
    "main,args",
    [
        (worker_main, []),
        (worker_main, ["--poll"]),
        (enqueue_main, []),
        (enqueue_main, ["--all", "--document-id", "x"]),
        (enqueue_main, ["--retry-job", "bad"]),
    ],
)
def test_invalid_cli_exits_two(main, args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_invalid_environment_is_safe(monkeypatch, capsys):
    monkeypatch.setattr(
        "support_copilot.bootstrap.build_embedding_worker",
        lambda: (_ for _ in ()).throw(ValueError("secret")),
    )
    assert worker_main(["--once"]) == 2
    assert "secret" not in capsys.readouterr().out


def test_lease_validation():
    with pytest.raises(ValidationError):
        WorkerSettings(
            _env_file=None,
            database_url="postgresql://unused",
            model_id="00000000-0000-0000-0000-000000000001",
            model_name="approved/test",
            model_revision="a" * 40,
            dimensions=3,
            tokenizer_limit=128,
            document_prompt="",
            query_prompt="",
            lease_seconds=10,
            heartbeat_seconds=10,
        )
