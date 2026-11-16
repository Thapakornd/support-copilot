"""Immutable processing identities and safe errors, independent of adapters."""

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from uuid import UUID


class ProcessingError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class OwnershipLost(ProcessingError):
    def __init__(self):
        super().__init__("ownership_lost")


def canonical_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmbeddingConfig:
    model_id: UUID
    model_name: str
    model_revision: str
    dimensions: int
    tokenizer_limit: int
    document_prompt: str
    query_prompt: str
    chunker_version: str = "heading-token-v1"
    target_chars: int = 2400
    max_document_tokens: int = 100_000
    max_document_chunks: int = 2000
    normalize: bool = True
    provider: str = "sentence-transformers"

    def __post_init__(self):
        if not isinstance(self.model_id, UUID) or not self.model_name.strip():
            raise ValueError("Model UUID and identifier are required")
        if not re.fullmatch(r"[0-9a-f]{40}", self.model_revision):
            raise ValueError("Model revision must be a pinned 40-character commit SHA")
        if (
            min(
                self.dimensions,
                self.tokenizer_limit,
                self.max_document_tokens,
                self.max_document_chunks,
            )
            <= 0
        ):
            raise ValueError("Dimensions and budgets must be positive")
        if (
            self.target_chars < 100
            or not self.normalize
            or self.chunker_version != "heading-token-v1"
        ):
            raise ValueError("Unsupported chunking/normalization policy")
        if not isinstance(self.document_prompt, str) or not isinstance(
            self.query_prompt, str
        ):
            raise TypeError("Explicit prompt strings required (empty is allowed)")

    def canonical_json(self) -> str:
        return canonical_json({**asdict(self), "model_id": str(self.model_id)})

    @property
    def config_hash(self) -> str:
        return sha256(self.canonical_json())

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**{**value, "model_id": UUID(str(value["model_id"]))})


@dataclass(frozen=True)
class EmbeddingJob:
    id: UUID
    document_id: str
    revision_id: UUID
    generation: int
    config: EmbeddingConfig
    attempts: int
    claim_token: UUID


@dataclass
class RecoveryResult:
    recovered: int = 0
    failed: int = 0
    superseded: int = 0


@dataclass
class QueueObservation:
    blocked: int = 0
    owned_elsewhere: int = 0
    deferred: int = 0


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int) -> None:
    if not count or len(vectors) != count:
        raise ProcessingError("vector_coverage")
    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(v) for v in vector):
            raise ProcessingError("vector_dimensions_or_finiteness")
        norm = math.sqrt(sum(v * v for v in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
            raise ProcessingError("vector_not_normalized")
