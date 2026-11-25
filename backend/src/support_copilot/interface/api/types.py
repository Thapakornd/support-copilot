from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel


def _reject_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("NUL characters are not allowed")
    return value


# PostgreSQL cannot store NUL; use for every inbound string (body and query).
NoNul = Annotated[str, AfterValidator(_reject_nul)]


def text(max_length: int, min_length: int = 0):
    """Trimmed, NUL-free string with length limits (checked after trimming)."""
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
        AfterValidator(_reject_nul),
    ]


class ApiModel(BaseModel):
    """camelCase JSON; request bodies forbid unknown fields."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )
