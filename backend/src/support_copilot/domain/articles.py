"""Pure article presentation rules: labels and plain-text excerpts."""

import re

_SOURCE_TYPES = {
    "documentation": "Documentation",
    "knowledge-article": "Knowledge Article",
    "community-forum": "Community Forum",
    "video": "Video",
}
_PRODUCTS = {
    "mongodb-atlas": "Atlas",
    "mongodb-server": "Server",
    "mongodb-drivers": "Drivers",
    "mongodb-ops-manager": "Ops Manager",
}
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# Stored excerpts are cut at a fixed length, so the last link may be unclosed.
_CUT_LINK = re.compile(r"(?:(?<=\s)|^)\[([^\[\]]*)(?:\](?:\([^)]*)?)?$")


def source_type_label(value: str) -> str:
    if value in _SOURCE_TYPES.values():
        return value
    return _SOURCE_TYPES.get(value, "Documentation")


def product_label(value: str) -> str:
    if value in _PRODUCTS.values():
        return value
    return _PRODUCTS.get(value, "Server")


def clean_excerpt(markdown: str) -> str:
    lines = (ln for ln in markdown.splitlines() if not ln.lstrip().startswith("#"))
    text = _LINK.sub(r"\1", "\n".join(lines))
    for mark in ("**", "__", "`"):
        text = text.replace(mark, "")
    return _CUT_LINK.sub(r"\1", " ".join(text.split()))


def display_body(value) -> dict | None:
    """Return {steps, note?} only when the stored value already has that shape."""
    if not isinstance(value, dict):
        return None
    steps, note = value.get("steps"), value.get("note")
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        return None
    if note is not None and not isinstance(note, str):
        return None
    return {"steps": steps} | ({"note": note} if note is not None else {})
