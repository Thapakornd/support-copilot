import pytest

from support_copilot.domain.articles import (
    clean_excerpt,
    display_body,
    product_label,
    source_type_label,
)


def test_excerpt_drops_headings_links_emphasis_and_whitespace():
    raw = "# Title\n\nUse **bold** and __under__ `code`.\n\n## Sub\nSee [the docs](https://x.test/a?b=1) now\n\n\n  end "
    assert clean_excerpt(raw) == "Use bold and under code. See the docs now end"


def test_excerpt_of_only_a_heading_is_empty():
    assert clean_excerpt("# Only a heading") == ""


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("documentation", "Documentation"),
        ("knowledge-article", "Knowledge Article"),
        ("community-forum", "Community Forum"),
        ("video", "Video"),
        ("Video", "Video"),
        ("Knowledge Article", "Knowledge Article"),
        ("weird", "Documentation"),
    ],
)
def test_source_type_label(raw, label):
    assert source_type_label(raw) == label


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("mongodb-atlas", "Atlas"),
        ("mongodb-server", "Server"),
        ("mongodb-drivers", "Drivers"),
        ("mongodb-ops-manager", "Ops Manager"),
        ("Ops Manager", "Ops Manager"),
        ("weird", "Server"),
    ],
)
def test_product_label(raw, label):
    assert product_label(raw) == label


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"steps": ["a", "b"], "note": "n"}, {"steps": ["a", "b"], "note": "n"}),
        ({"steps": ["a"]}, {"steps": ["a"]}),
        (None, None),
        ({"note": "n"}, None),
        ({"steps": "a"}, None),
        ({"steps": [1]}, None),
        ({"steps": ["a"], "note": 3}, None),
        ("text", None),
    ],
)
def test_display_body_only_when_steps_shape_holds(value, expected):
    assert display_body(value) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A [replica se", "A replica se"),
        (
            "You can [create and manage unique indexe",
            "You can create and manage unique indexe",
        ),
        (
            "create a [compound index](https://www.mongodb.com/docs/",
            "create a compound index",
        ),
        ("create a [compound index]", "create a compound index"),
        ("create a [compound index](", "create a compound index"),
        ("arr[0] is first", "arr[0] is first"),
        ("see [a](u) then arr[1] and [b", "see a then arr[1] and b"),
    ],
)
def test_truncated_trailing_link_reduces_to_its_text(raw, expected):
    assert clean_excerpt(raw) == expected
