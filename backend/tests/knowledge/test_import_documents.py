import json
from unittest.mock import patch

import psycopg
import pytest

from support_copilot.knowledge.import_documents import load_documents, main


def document(**changes):
    return {
        "document_id": "doc_demo",
        "title": "Example",
        "source_url": "https://example.test/",
        "content_markdown": '# Example\n\nUnicode: ภาษาไทย. Quotes: "hello". Backslash: \\.',
        **changes,
    }


def write_file(tmp_path, rows):
    path = tmp_path / "documents.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_preserves_markdown_and_unicode(tmp_path):
    rows = [document()]
    loaded = load_documents(write_file(tmp_path, rows))
    assert loaded == rows


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [document(), document()],
        [document(title="")],
        [document(), {"chunk_id": "wrong-file"}],
        [42],
    ],
)
def test_rejects_invalid_documents_before_database_access(tmp_path, rows):
    path = write_file(tmp_path, rows)
    with patch("psycopg.connect") as run:
        assert main(["--file", str(path)]) == 2
    run.assert_not_called()


def test_dry_run_validates_without_database(tmp_path, capsys):
    path = write_file(tmp_path, [document()])
    with patch("psycopg.connect") as run:
        assert main(["--file", str(path), "--dry-run"]) == 0
    run.assert_not_called()
    assert "1 documents" in capsys.readouterr().out


def test_malformed_json_has_line_number(tmp_path):
    path = write_file(tmp_path, [document()])
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\nnot-json")
    with pytest.raises(ValueError, match="line 2"):
        load_documents(path)


@pytest.mark.parametrize(
    "metadata",
    [
        {"nested": ["bad\x00text"]},
        {"bad\x00key": "value"},
        {"nested": ["\ud800"]},
        {"\udfff": "value"},
    ],
)
def test_rejects_strings_postgres_jsonb_cannot_store(tmp_path, metadata):
    path = write_file(tmp_path, [document(metadata=metadata)])
    with patch("psycopg.connect") as run:
        assert main(["--file", str(path), "--dry-run"]) == 2
    run.assert_not_called()


def test_database_failure_is_not_reported_as_success(tmp_path, capsys, monkeypatch):
    path = write_file(tmp_path, [document()])
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:private-password@db/app")
    with patch(
        "psycopg.connect", side_effect=psycopg.OperationalError("private-password")
    ) as connect:
        assert main(["--file", str(path)]) == 1
        assert connect.call_args.args[0] == "postgresql://app:private-password@db/app"
    captured = capsys.readouterr()
    assert "Imported" not in captured.out
    assert "private-password" not in captured.err


def test_missing_database_configuration_is_safe(tmp_path, capsys, monkeypatch):
    from support_copilot.core.config import Settings

    path = write_file(tmp_path, [document()])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "support_copilot.knowledge.import_documents.Settings",
        lambda: Settings(_env_file=None),
        raising=False,
    )
    with patch("psycopg.connect") as connect:
        assert main(["--file", str(path)]) == 2
    connect.assert_not_called()
    assert "DATABASE_URL" in capsys.readouterr().err
