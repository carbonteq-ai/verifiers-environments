"""Minimal immutable model values shared by manifest capabilities."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictStr

Identifier = Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
