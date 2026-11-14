import csv
import io
import json
from unittest.mock import patch

import pytest

from support_copilot.knowledge.import_documents import build_sql, load_documents, main


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


def test_copy_serialization_roundtrips_markdown_and_unicode(tmp_path):
    rows = [document()]
    loaded = load_documents(write_file(tmp_path, rows))
    sql = build_sql(loaded)
    copy_data = sql.split("FROM STDIN WITH (FORMAT csv);\n", 1)[1].split("\\.\n", 1)[0]
    assert [json.loads(row[0]) for row in csv.reader(io.StringIO(copy_data))] == rows
    assert "ON CONFLICT (document_id) DO UPDATE" in sql
    assert sql.startswith("BEGIN;")
    assert sql.rstrip().endswith("COMMIT;")
    assert "knowledge_chunks" not in sql


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
    with patch("subprocess.run") as run:
        assert main(["--file", str(path)]) == 2
    run.assert_not_called()


def test_dry_run_validates_without_docker(tmp_path, capsys):
    path = write_file(tmp_path, [document()])
    with patch("subprocess.run") as run:
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
    with patch("subprocess.run") as run:
        assert main(["--file", str(path), "--dry-run"]) == 2
    run.assert_not_called()


def test_database_failure_is_not_reported_as_success(tmp_path, capsys):
    path = write_file(tmp_path, [document()])
    with patch("subprocess.run") as run:
        run.return_value.returncode = 1
        assert main(["--file", str(path)]) == 1
        assert run.call_args.kwargs["encoding"] == "utf-8"
        assert "ON_ERROR_STOP=1" in run.call_args.args[0]
    assert "Imported" not in capsys.readouterr().out
