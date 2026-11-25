import json
from datetime import datetime
from uuid import uuid4

import psycopg
import pytest

H = {"X-Demo-User": "customer"}


def add_article(
    db,
    document_id,
    *,
    title="Title",
    excerpt="# Title\n\nPlain excerpt",
    content="# Title\n\nbody text",
    category="connectivity",
    source_type="knowledge-article",
    product="mongodb-atlas",
    fetched_at="2026-11-16T00:00:00Z",
    display_body=None,
    active=True,
    staged=False,
    source_url="https://example.org/a",
):
    revision_id = uuid4()
    with psycopg.connect(db) as conn:
        conn.execute(
            "INSERT INTO knowledge_documents(document_id, data, is_active) VALUES (%s, '{}', %s)",
            (document_id, active),
        )
        conn.execute(
            """INSERT INTO knowledge_document_revisions
               (id, document_id, revision_hash, content_hash, title, source_url, source_type,
                product, deployment, version_scope, category_id, topics, content_markdown,
                excerpt, display_body, source_payload, fetched_at)
               VALUES (%s,%s,'h','c',%s,%s,%s,%s,'atlas','current',%s,'{}',%s,%s,%s,'{}',%s)""",
            (
                revision_id,
                document_id,
                title,
                source_url,
                source_type,
                product,
                category,
                content,
                excerpt,
                json.dumps(display_body) if display_body else None,
                fetched_at,
            ),
        )
        if not staged:
            conn.execute(
                "UPDATE knowledge_documents SET current_revision_id=%s WHERE document_id=%s",
                (revision_id, document_id),
            )


def ids(api, path, **params):
    response = api.get(path, params=params, headers=H)
    assert response.status_code == 200
    return [a["id"] for a in response.json()]


def test_list_orders_newest_first_then_id_and_maps_labels(api, db):
    add_article(db, "b", fetched_at="2026-11-10T00:00:00Z")
    add_article(
        db,
        "a",
        fetched_at="2026-11-10T00:00:00Z",
        source_type="video",
        product="mongodb-ops-manager",
    )
    add_article(
        db,
        "c",
        fetched_at="2026-11-20T10:30:00+07:00",
        source_type="odd",
        product="odd",
    )
    response = api.get("/articles", headers=H)
    assert response.status_code == 200
    items = response.json()
    assert [i["id"] for i in items] == ["c", "a", "b"]
    assert {k: v for k, v in items[0].items() if k != "updated"} == {
        "id": "c",
        "title": "Title",
        "type": "Documentation",
        "product": "Server",
        "topic": "connectivity",
        "excerpt": "Plain excerpt",
    }
    assert (items[1]["type"], items[1]["product"]) == ("Video", "Ops Manager")


def test_updated_is_iso_8601_with_an_offset(api, db):
    add_article(db, "a", fetched_at="2026-11-20T10:30:00+00:00")
    updated = api.get("/articles", headers=H).json()[0]["updated"]
    parsed = datetime.fromisoformat(updated)
    assert parsed.utcoffset() is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 11, 20)


def test_inactive_and_staged_documents_are_invisible(api, db):
    add_article(db, "live", content="text")
    add_article(db, "off", active=False, content="text")
    add_article(db, "staged", staged=True, content="text")
    assert ids(api, "/articles") == ["live"]
    assert api.get("/articles/live", headers=H).status_code == 200
    assert api.get("/articles/off", headers=H).status_code == 404
    assert api.get("/articles/staged", headers=H).status_code == 404
    assert ids(api, "/articles/search", q="text") == ["live"]


def test_detail_has_content_source_url_and_body_only_for_steps(api, db):
    add_article(db, "plain", content="# T\n\n**md** body")
    add_article(db, "steps", display_body={"steps": ["one", "two"], "note": "n"})
    plain = api.get("/articles/plain", headers=H).json()
    assert plain["content"] == "# T\n\n**md** body"
    assert plain["sourceUrl"] == "https://example.org/a"
    assert "body" not in plain
    assert api.get("/articles/steps", headers=H).json()["body"] == {
        "steps": ["one", "two"],
        "note": "n",
    }


def test_excerpt_is_cleaned_plain_text(api, db):
    add_article(
        db, "a", excerpt="# Title\n\nSee [docs](https://x.test) **now**\n\n`code`"
    )
    assert api.get("/articles", headers=H).json()[0]["excerpt"] == "See docs now code"


def test_unknown_or_nul_path_id_is_404(api):
    assert api.get("/articles/missing", headers=H).status_code == 404
    assert api.get("/articles/a%00b", headers=H).status_code == 404


def test_articles_require_authentication(api):
    for path in ("/articles", "/articles/x", "/articles/search?q=a"):
        assert api.get(path).status_code == 401


def test_search_route_is_not_captured_by_the_id_route(api, db):
    add_article(db, "search", title="Search", content="alpha")
    response = api.get("/articles/search", params={"q": "alpha"}, headers=H)
    assert response.status_code == 200
    assert [a["id"] for a in response.json()] == ["search"]


def test_search_matches_any_word_of_a_sentence_best_first(api, db):
    add_article(
        db, "both", title="Network peering route", content="peering route table"
    )
    add_article(db, "one", title="Other", content="the route is here")
    add_article(db, "none", title="Unrelated", content="nothing relevant")
    q = "How do I fix my peering route problem?"
    assert ids(api, "/articles/search", q=q) == ["both", "one"]


def test_title_match_outranks_a_long_document(api, db):
    add_article(db, "title", title="Peering guide", content="short page")
    add_article(db, "long", title="Giant", content="peering " * 8000 + "x" * 60000)
    assert ids(api, "/articles/search", q="peering") == ["title", "long"]


def test_topic_filter_and_unknown_topic(api, db):
    add_article(db, "a", category="connectivity", content="alpha")
    add_article(db, "b", category="security", content="alpha")
    assert ids(api, "/articles/search", q="alpha", topic="security") == ["b"]
    assert sorted(ids(api, "/articles/search", q="alpha")) == ["a", "b"]
    assert ids(api, "/articles/search", q="alpha", topic="nope") == []
    assert ids(api, "/articles/search", q="", topic="security") == ["b"]


def test_blank_query_lists_in_list_order_and_stop_words_return_nothing(api, db):
    add_article(db, "old", fetched_at="2026-01-01T00:00:00Z")
    add_article(db, "new", fetched_at="2026-02-01T00:00:00Z")
    assert ids(api, "/articles/search", q="") == ["new", "old"]
    assert ids(api, "/articles/search", q="   ") == ["new", "old"]
    assert ids(api, "/articles/search") == ["new", "old"]
    assert ids(api, "/articles/search", q="the of and") == []
    assert ids(api, "/articles/search", q="!!! ???") == []


@pytest.mark.parametrize(
    "q",
    [
        'it\'s "quoted" & piped | negated ! colon: star* (paren) ((',
        "https://example.com/a?b=1&c=2#frag http://x",
        "well-known state-of-the-art re-election",
        "back\\slash \\ \\\\ trailing\\",
        "a:b <-> c <3> d'e ''' &&& ||| !!!",
        "x" * 3000,
        " ".join(f"word{i}" for i in range(500)),
        "é ü 日本語 🙂",
    ],
)
def test_hostile_queries_never_fail(api, db, q):
    add_article(db, "a", content="well-known quoted")
    ids(api, "/articles/search", q=q)


def test_hyphenated_words_still_match(api, db):
    add_article(db, "a", title="Well-known endpoint", content="x")
    assert ids(api, "/articles/search", q="well-known") == ["a"]


def test_search_limits_to_50_and_orders_ties_by_id(api, db):
    for i in range(55):
        add_article(db, f"d{i:02d}", title="Same", content="alpha")
    assert ids(api, "/articles/search", q="alpha") == [f"d{i:02d}" for i in range(50)]


def test_search_input_validation(api):
    def status(**params):
        return api.get("/articles/search", params=params, headers=H).status_code

    assert status(q="a\x00b") == 422
    assert status(q="ok", topic="a\x00") == 422
    assert status(q="x" * 4001) == 422
    assert status(q="x" * 4000) == 200


def test_long_page_does_not_win_on_length_alone(api, db):
    filler = "unrelated words about something else entirely " * 1500
    add_article(
        db, "long", title="Giant", content=f"peering {filler} peering {filler} peering"
    )
    add_article(db, "short", title="Short", content="peering explained briefly")
    assert ids(api, "/articles/search", q="peering") == ["short", "long"]
