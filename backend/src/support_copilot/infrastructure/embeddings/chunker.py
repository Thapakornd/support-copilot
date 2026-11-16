"""Heading-aware preparation refined against the actual prompted tokenizer."""

from support_copilot.domain.embedding_job import ProcessingError, sha256
from support_copilot.knowledge.prepare import _blocks, chunk_document


class TokenAwareChunker:
    def chunks(self, snapshot, config, encoder):
        content = snapshot.get("content_markdown", "")
        if not content.strip():
            raise ProcessingError("empty_document")
        if encoder.token_count(content) > config.max_document_tokens:
            raise ProcessingError("document_budget")
        # fetch_url is transport-only and may be absent in a promoted payload.
        document = {"fetch_url": snapshot["source_url"], **snapshot}
        try:
            prepared = chunk_document(document, target_chars=config.target_chars)
        except (KeyError, ValueError):
            raise ProcessingError("invalid_source") from None
        if not prepared:
            raise ProcessingError("empty_document")
        result = []
        total_tokens = 0

        def add(original, text):
            nonlocal total_tokens
            tokens = encoder.token_count(text)
            if tokens > config.tokenizer_limit:
                raise ProcessingError("oversized_block")
            total_tokens += tokens
            if (
                len(result) >= config.max_document_chunks
                or total_tokens > config.max_document_tokens
            ):
                raise ProcessingError("document_budget")
            index = len(result)
            result.append(
                {
                    **original,
                    "text": text,
                    "char_count": len(text),
                    "oversized": False,
                    "chunk_index": index,
                    "chunk_id": "chunk_"
                    + sha256(
                        f"{snapshot['document_id']}:{snapshot['content_hash']}:{config.config_hash}:{index}:{text}"
                    )[:32],
                }
            )

        for original in prepared:
            text = original["text"]
            if encoder.token_count(text) <= config.tokenizer_limit:
                add(original, text)
                continue
            blocks = list(_blocks(text))
            heading = "\n\n".join(
                block for kind, block, _ in blocks if kind == "heading"
            )
            prefix = heading + "\n\n" if heading else ""
            if encoder.token_count(prefix) >= config.tokenizer_limit:
                raise ProcessingError("heading_overhead")
            for kind, block, indivisible in blocks:
                if kind == "heading":
                    continue
                if indivisible:
                    if encoder.token_count(prefix + block) > config.tokenizer_limit:
                        raise ProcessingError("oversized_block")
                    add(original, prefix + block)
                    continue
                remaining = block
                while remaining:
                    # Find a fitting character prefix without assuming tokens == chars.
                    low, high = 0, len(remaining)
                    while low < high:
                        mid = (low + high + 1) // 2
                        if (
                            encoder.token_count(prefix + remaining[:mid])
                            <= config.tokenizer_limit
                        ):
                            low = mid
                        else:
                            high = mid - 1
                    if low == 0:
                        raise ProcessingError("heading_overhead")
                    add(original, prefix + remaining[:low])
                    remaining = remaining[low:]
        return result
