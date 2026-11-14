import pytest

from support_copilot.knowledge.prepare import chunk_document, prepare_document

SOURCE = {
    "source_url": "https://www.mongodb.com/docs/atlas/troubleshoot-connection/",
    "fetch_url": "https://www.mongodb.com/docs/atlas/troubleshoot-connection.md",
    "product": "mongodb-atlas",
    "deployment": "atlas",
    "version_scope": "current-unversioned",
    "category": "Connectivity",
    "topics": ["connection-errors", "dns"],
}


def prepare(text):
    return prepare_document(SOURCE, text, "2026-11-14T00:00:00+00:00")


def test_normalizes_markdown_without_destroying_code():
    doc = prepare(
        "---\nlayout: docs\n---\n> This page location: /docs.md\n\n"
        "<!-- tab metadata -->\n# Connection Help\n\n"
        "Use the following command.\n\n```sh\n  mongosh --help\n\n```\n"
    )
    assert doc["title"] == "Connection Help"
    assert doc["content_markdown"].startswith("# Connection Help")
    assert "  mongosh --help\n\n```" in doc["content_markdown"]
    assert "layout:" not in doc["content_markdown"]
    assert "tab metadata" not in doc["content_markdown"]
    assert doc["version_scope"] == "current-unversioned"
    assert doc["source_url"] == SOURCE["source_url"]


def test_ids_are_stable_and_content_changes_have_distinct_hashes():
    first = prepare("# Help\n\nOriginal guidance.")
    same = prepare_document(SOURCE, "# Help\n\nOriginal guidance.", "later")
    changed = prepare("# Help\n\nUpdated guidance.")
    assert first["document_id"] == same["document_id"] == changed["document_id"]
    assert first["content_hash"] == same["content_hash"] != changed["content_hash"]
    assert chunk_document(first) == chunk_document(same)
    assert (
        chunk_document(first)[0]["chunk_id"] != chunk_document(changed)[0]["chunk_id"]
    )


def test_chunks_have_heading_context_and_code_headings_are_not_sections():
    text = (
        "# Help\n\nOverview.\n\n## DNS\n\nCheck DNS.\n\n"
        "```sh\n# This is a shell comment\nnslookup example.test\n```\n\n"
        "### Windows\n\nUse PowerShell.\n\n## Authentication\n\nCheck credentials."
    )
    chunks = chunk_document(prepare(text), target_chars=240)
    assert [c["heading_path"] for c in chunks] == [
        ["Help"],
        ["Help", "DNS"],
        ["Help", "DNS", "Windows"],
        ["Help", "Authentication"],
    ]
    dns = chunks[1]
    assert "```sh\n# This is a shell comment\nnslookup example.test\n```" in dns["text"]
    assert dns["source_url"] == SOURCE["source_url"]
    assert dns["category"] == "Connectivity"
    assert dns["document_id"] == prepare(text)["document_id"]
    assert all(c["char_count"] == len(c["text"]) for c in chunks)


def test_large_paragraphs_split_and_oversized_code_is_explicit():
    code = "```python\n" + ("print('hello')\n" * 40) + "```"
    doc = prepare("# Help\n\n" + "Sentence. " * 100 + "\n\n" + code)
    chunks = chunk_document(doc, target_chars=240)
    assert len(chunks) > 2
    normal = [c for c in chunks if "```python" not in c["text"]]
    assert all(len(c["text"]) <= 240 for c in normal)
    oversized = [c for c in chunks if c["oversized"]]
    assert len(oversized) == 1
    assert code in oversized[0]["text"]
    assert sum(c["text"].count("Sentence.") for c in chunks) == 100


def test_tilde_fences_and_tables_are_kept_whole():
    code = "~~~~text\n## not a heading\n~~~\n~~~~"
    table = "| Key | Value |\n| --- | --- |\n" + "| x | y |\n" * 30
    chunks = chunk_document(prepare("# Help\n\n" + code + "\n\n" + table), 100)
    assert any(code in c["text"] for c in chunks)
    assert any(table.strip() in c["text"] for c in chunks)
    assert all(c["heading_path"] == ["Help"] for c in chunks)


def test_list_local_headings_do_not_scope_later_common_steps():
    markdown = (
        "# Connect\n\n## Procedure\n\n"
        "3. Choose a connection type.\n\n"
        "   ### Private Endpoint Connection\n\n"
        "   This option needs a private endpoint.\n\n"
        "4. Select Drivers.\n\n"
        "5. Select your driver and version.\n"
    )
    doc = prepare(markdown)
    assert "\n   ### Private Endpoint Connection\n" in doc["content_markdown"]
    assert "\n   This option" in doc["content_markdown"]
    chunks = chunk_document(doc, 160)
    common_step = next(c for c in chunks if "4. Select Drivers" in c["text"])
    assert common_step["heading_path"] == ["Connect", "Procedure"]
    assert all("Private Endpoint Connection" not in c["heading_path"] for c in chunks)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "<!doctype html><html><h1>Blocked</h1></html>",
        "# Empty",
        "No document title here.",
    ],
)
def test_rejects_empty_or_non_document_content(text):
    with pytest.raises(ValueError):
        prepare(text)
