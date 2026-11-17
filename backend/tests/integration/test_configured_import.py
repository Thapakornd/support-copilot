import json

import psycopg

from support_copilot.knowledge.import_documents import main


def test_importer_uses_shared_database_and_upserts_unicode(db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db)
    path = tmp_path / "documents.jsonl"
    document = {
        "document_id": "doc-config-import",
        "title": "Example",
        "source_url": "https://example.test",
        "content_markdown": 'ภาษาไทย "quoted" \\ text\nnext line',
        "metadata": {"nested": ["preserved"]},
    }
    for title in ("Original", "Updated"):
        document["title"] = title
        path.write_text(json.dumps(document), encoding="utf-8")
        assert main(["--file", str(path)]) == 0
        with psycopg.connect(db) as conn:
            rows = conn.execute(
                "SELECT data FROM knowledge_documents WHERE document_id=%s",
                ("doc-config-import",),
            ).fetchall()
        assert rows == [(document,)]
