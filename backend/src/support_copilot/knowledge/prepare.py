"""Normalize Markdown and build deterministic, citation-ready records."""

import hashlib
import re

SCHEMA_VERSION = 1
METADATA_FIELDS = (
    "source_url",
    "fetch_url",
    "title",
    "product",
    "deployment",
    "version_scope",
    "category",
    "topics",
    "source_type",
)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _blocks(text: str):
    """Yield complete fences, headings, and blank-line-separated blocks."""
    lines = []
    fence = None
    for line in text.splitlines():
        marker = FENCE.match(line)
        if fence:
            lines.append(line)
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                yield "block", "\n".join(lines), True
                lines, fence = [], None
        elif marker:
            if lines:
                yield "block", "\n".join(lines), False
            lines, fence = [line], marker[1]
        elif HEADING.match(line):
            if lines:
                yield "block", "\n".join(lines), False
                lines = []
            yield "heading", line, False
        elif not line.strip():
            if lines:
                block = "\n".join(lines)
                yield "block", block, block.lstrip().startswith("|")
                lines = []
        else:
            lines.append(line)
    if fence:
        raise ValueError("Unclosed Markdown code fence")
    if lines:
        block = "\n".join(lines)
        yield "block", block, block.lstrip().startswith("|")


def prepare_document(source: dict, markdown: str, fetched_at: str) -> dict:
    """Keep source Markdown as evidence; remove frontmatter and docs scaffolding."""
    text = markdown.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if re.search(r"<!doctype\s+html|<html\b", text[:1000], re.IGNORECASE):
        raise ValueError("Received HTML instead of Markdown")
    if text.startswith("---\n"):
        frontmatter = re.match(r"\A---\n.*?\n---(?:\n|$)", text, re.DOTALL)
        if not frontmatter:
            raise ValueError("Unclosed Markdown frontmatter")
        text = text[frontmatter.end() :]
    # The official Markdown export has navigation/tab hints before its first H1.
    blocks = list(_blocks(text))
    start = next(
        (
            i
            for i, (kind, block, _) in enumerate(blocks)
            if kind == "heading" and block.startswith("# ")
        ),
        None,
    )
    if start is None:
        raise ValueError("Document has no H1 title")
    blocks = blocks[start:]
    title = HEADING.match(blocks[0][1])[2]
    cleaned = []
    for _, block, indivisible in blocks:
        if not indivisible:
            # Leading indentation carries list/tab scope. Removing it can turn a
            # list-local heading into a false section for subsequent common steps.
            block = re.sub(r"<!--.*?-->", "", block, flags=re.DOTALL).strip("\n")
        if block.strip():
            cleaned.append(block)
    content = "\n\n".join(cleaned).strip() + "\n"
    if not any(
        kind == "block" and block.strip() for kind, block, _ in _blocks(content)
    ):
        raise ValueError("Document has no body content")
    return {
        "schema_version": SCHEMA_VERSION,
        **{key: source[key] for key in METADATA_FIELDS if key in source},
        "source_type": "documentation",
        "document_id": "doc_" + digest(source["source_url"])[:24],
        "title": title,
        "content_markdown": content,
        "content_hash": digest(content),
        "fetched_at": fetched_at,
    }


def _split_text(text: str, budget: int):
    while len(text) > budget:
        boundary = text.rfind(" ", 0, budget + 1)
        if boundary < budget // 2:
            boundary = budget
        yield text[:boundary].rstrip()
        text = text[boundary:].lstrip()
    if text:
        yield text


def chunk_document(document: dict, target_chars: int = 2400) -> list[dict]:
    """Split sections by characters; keep fences/tables whole even when oversized.

    This is deliberately not a token count. Heading context is repeated in text,
    and each record exposes char_count and oversized for import-time decisions.
    """
    if target_chars < 100:
        raise ValueError("target_chars must be at least 100")
    chunks = []
    headings = []
    pending = []

    def prefix():
        return "\n\n".join("#" * level + " " + title for level, title in headings)

    def flush():
        if not pending:
            return
        text = prefix() + "\n\n" + "\n\n".join(pending)
        index = len(chunks)
        chunks.append(
            {
                "schema_version": SCHEMA_VERSION,
                **{key: document[key] for key in METADATA_FIELDS},
                "document_id": document["document_id"],
                "document_content_hash": document["content_hash"],
                "chunk_id": "chunk_"
                + digest(
                    f"{document['document_id']}:{document['content_hash']}:{index}:{text}"
                )[:24],
                "chunk_index": index,
                "heading_path": [title for _, title in headings],
                "text": text,
                "char_count": len(text),
                "oversized": len(text) > target_chars,
            }
        )
        pending.clear()

    for kind, block, indivisible in _blocks(document["content_markdown"]):
        if kind == "heading":
            flush()
            match = HEADING.match(block)
            level, title = len(match[1]), match[2]
            headings = [(n, t) for n, t in headings if n < level] + [(level, title)]
            continue
        budget = max(1, target_chars - len(prefix()) - 2)
        pieces = [block] if indivisible else list(_split_text(block, budget))
        for piece in pieces:
            if pending and len("\n\n".join([*pending, piece])) > budget:
                flush()
            pending.append(piece)
            if indivisible and len(piece) > budget:
                flush()
    flush()
    return chunks
