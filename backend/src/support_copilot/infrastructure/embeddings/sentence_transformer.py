"""Shared query/document encoder with explicit prompts and pinned local artifacts."""

import math

from support_copilot.domain.embedding_job import ProcessingError, validate_vectors


class SentenceTransformerEncoder:
    def __init__(self, config, *, device="cpu", batch_size=32, offline=True):
        self.config = config
        self.device = device
        self.batch_size = batch_size
        self.offline = offline
        self._model = None
        if batch_size <= 0:
            raise ValueError("Batch size must be positive")

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    self.config.model_name,
                    revision=self.config.model_revision,
                    device=self.device,
                    local_files_only=self.offline,
                    trust_remote_code=False,
                )
            except (ImportError, OSError, ValueError, RuntimeError):
                raise ProcessingError("model_unavailable") from None
            if model.get_sentence_embedding_dimension() != self.config.dimensions:
                raise ProcessingError("model_dimension_mismatch")
            if self.config.tokenizer_limit > model.max_seq_length:
                raise ProcessingError("tokenizer_limit_mismatch")
            model.max_seq_length = self.config.tokenizer_limit
            self._model = model
        return self._model

    def token_count(self, text, *, query=False):
        model = self._load()
        prompt = self.config.query_prompt if query else self.config.document_prompt
        return len(
            model.tokenizer(prompt + text, add_special_tokens=True, truncation=False)[
                "input_ids"
            ]
        )

    def _encode(self, texts, *, query):
        model = self._load()
        if any(
            self.token_count(text, query=query) > self.config.tokenizer_limit
            for text in texts
        ):
            raise ProcessingError("oversized_block")
        method = model.encode_query if query else model.encode_document
        try:
            result = method(
                texts,
                prompt=self.config.query_prompt
                if query
                else self.config.document_prompt,
                normalize_embeddings=False,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).tolist()
        except (MemoryError, RuntimeError):
            raise ProcessingError("encoding_resource", retryable=True) from None

        # Normalize Python floats so float16 model output meets the unit-norm check.
        for index, vector in enumerate(result):
            norm = math.hypot(*vector)
            if norm > 0 and math.isfinite(norm):
                result[index] = [value / norm for value in vector]
        validate_vectors(result, len(texts), self.config.dimensions)
        return result

    def encode_documents(self, texts):
        return self._encode(texts, query=False)

    def encode_queries(self, texts):
        return self._encode(texts, query=True)
