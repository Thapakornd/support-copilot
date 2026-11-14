import json

import httpx
import pytest

from support_copilot.knowledge.cli import main, run_pipeline
from support_copilot.knowledge.download import Downloader
from support_copilot.knowledge.prepare import digest

ROOT = "https://www.mongodb.com"
URL = ROOT + "/docs/atlas/troubleshoot-connection.md"
SOURCE = {
    "source_url": ROOT + "/docs/atlas/troubleshoot-connection/",
    "fetch_url": URL,
    "product": "mongodb-atlas",
    "deployment": "atlas",
    "version_scope": "current-unversioned",
    "category": "Connectivity",
    "topics": ["connection-errors"],
}
MARKDOWN = (
    "# Troubleshoot Connection Issues\n\n## DNS\n\nCheck the DNS configuration.\n"
)


def client(handler):
    def route(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /docs/private/\n")
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(route))


def manifest(tmp_path, sources=None):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(sources or [SOURCE]), encoding="utf-8")
    return path


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_pipeline_exports_real_documents_chunks_and_offline_rebuild(
    tmp_path, line_ending
):
    config = manifest(tmp_path)
    out = tmp_path / "output"
    with client(
        lambda req: httpx.Response(200, text=MARKDOWN.replace("\n", line_ending))
    ) as http:
        report = run_pipeline(config, out, client=http, delay=0)
    assert report["failed"] == 0
    assert report["document_count"] == 1
    assert report["chunk_count"] == 1
    docs = records(out / "documents.jsonl")
    chunks = records(out / "chunks.jsonl")
    assert docs[0]["title"] == "Troubleshoot Connection Issues"
    assert chunks[0]["document_id"] == docs[0]["document_id"]
    assert chunks[0]["source_url"] == SOURCE["source_url"]
    assert list((out / "raw").glob("*.md"))
    before = [(out / name).read_bytes() for name in ["documents.jsonl", "chunks.jsonl"]]

    def no_network(request):
        pytest.fail("Offline preparation accessed the network")

    with httpx.Client(transport=httpx.MockTransport(no_network)) as http:
        again = run_pipeline(config, out, offline=True, client=http, delay=0)
    assert again["failed"] == 0
    assert before == [
        (out / name).read_bytes() for name in ["documents.jsonl", "chunks.jsonl"]
    ]


def test_partial_failure_is_explicit_and_never_reuses_stale_documents(tmp_path):
    config, out = manifest(tmp_path), tmp_path / "output"
    with client(lambda req: httpx.Response(200, text=MARKDOWN)) as http:
        run_pipeline(config, out, client=http, delay=0)
    with client(lambda req: httpx.Response(404)) as http:
        report = run_pipeline(config, out, client=http, delay=0)
    assert report["failed"] == 1
    assert "404" in report["sources"][0]["error"]
    assert records(out / "documents.jsonl") == []
    assert records(out / "chunks.jsonl") == []


def test_offline_missing_or_modified_snapshot_fails(tmp_path):
    config, out = manifest(tmp_path), tmp_path / "output"
    missing = run_pipeline(config, out, offline=True)
    assert missing["failed"] == 1
    with client(lambda req: httpx.Response(200, text=MARKDOWN)) as http:
        run_pipeline(config, out, client=http, delay=0)
    next((out / "raw").glob("*.md")).write_text(MARKDOWN + "tampered", encoding="utf-8")
    assert run_pipeline(config, out, offline=True)["failed"] == 1


def test_downloader_retries_429_and_caches_robots():
    calls, waits = [], []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, text=MARKDOWN)

    with client(handler) as http:
        downloader = Downloader(http, delay=0, sleep=waits.append)
        assert downloader.fetch(URL)["markdown"] == MARKDOWN
        assert downloader.fetch(URL)["markdown"] == MARKDOWN
    assert len(calls) == 3
    assert 2 in waits


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/docs/page.md",
        "http://www.mongodb.com/docs/page.md",
        ROOT + "/community/page.md",
        ROOT + "/docs/../secret.md",
        ROOT + "/docs/%2e%2e/secret.md",
        ROOT + "/docs/private/page.md",
    ],
)
def test_disallowed_urls_never_reach_document_endpoint(url):
    def forbidden(req):
        pytest.fail("A disallowed document URL was requested")

    with client(forbidden) as http, pytest.raises(ValueError):
        Downloader(http, delay=0).fetch(url)


def test_redirect_is_validated_before_following():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(
            302, headers={"Location": "https://example.com/stolen.md"}
        )

    with client(handler) as http, pytest.raises(ValueError):
        Downloader(http, delay=0).fetch(URL)
    assert calls == [URL]


def test_allowed_redirect_records_actual_url():
    def handler(req):
        if str(req.url) == URL:
            return httpx.Response(301, headers={"Location": "/docs/atlas/new-page.md"})
        return httpx.Response(200, text=MARKDOWN)

    with client(handler) as http:
        result = Downloader(http, delay=0).fetch(URL)
    assert result["resolved_fetch_url"] == ROOT + "/docs/atlas/new-page.md"
    assert result["raw_sha256"] == digest(MARKDOWN)


@pytest.mark.parametrize(
    "status,body",
    [(403, "blocked"), (200, "<html>Challenge</html>"), (500, "Unavailable")],
)
def test_unusable_robots_does_not_allow_documents(status, body):
    def handler(req):
        assert req.url.path == "/robots.txt"
        return httpx.Response(status, text=body)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ValueError),
    ):
        Downloader(http, delay=0, sleep=lambda _: None).fetch(URL)


@pytest.mark.parametrize(
    "sources",
    [
        [SOURCE, SOURCE],
        [{**SOURCE, "category": ""}],
        [{"source_url": SOURCE["source_url"]}],
    ],
)
def test_invalid_manifest_fails_before_network_or_exports(tmp_path, sources):
    config, out = manifest(tmp_path, sources), tmp_path / "output"
    with pytest.raises(ValueError):
        run_pipeline(config, out, offline=True)
    assert not out.exists()


def test_cli_returns_failure_for_missing_snapshot(tmp_path):
    config = manifest(tmp_path)
    assert (
        main(
            ["--manifest", str(config), "--output", str(tmp_path / "out"), "--offline"]
        )
        == 1
    )
