"""Separate redesign identity; historical collection scorer identities stay intact."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Literal

import pydantic
import verifiers
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..capture import canonical_json
from .verify import scorer_fingerprint


def revision_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class RedesignRevision(BaseModel):
    """Integrity identity, not proof of scientific approval or source authenticity."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1] = 1
    benchmark_scorer_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    native_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_digests: dict[str, str]
    configuration_json: str
    runtime: dict[str, str]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_identity(self) -> RedesignRevision:
        if (
            not self.source_digests
            or any(not key for key in self.source_digests)
            or any(
                len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
                for value in self.source_digests.values()
            )
        ):
            raise ValueError("redesign source closure requires source digests")
        configuration = json.loads(self.configuration_json)
        if not isinstance(configuration, dict):
            raise ValueError("redesign configuration must be an object")  # noqa: TRY004
        if canonical_json(configuration) != self.configuration_json:
            raise ValueError("redesign configuration must be canonical JSON")
        if set(self.runtime) != {"python", "pydantic"} or not all(self.runtime.values()):
            raise ValueError("redesign runtime identity is incomplete")
        if revision_digest(self.model_dump(mode="json", exclude={"digest"})) != self.digest:
            raise ValueError("redesign identity changed")
        return self


def capture_redesign_revision(
    configuration: dict[str, Any], native_source_digest: str
) -> RedesignRevision:
    """Hash actual adapter sources plus declared native code/configuration bindings.

    This conservative adapter closure includes the predicate, evidence adapter,
    publisher, task loader and calibration consumer. Native source provenance is
    supplied by composition's qualified source manifest. External custom policy
    code must also have an explicit digest in the selected configuration. Never
    put credentials in that configuration. Approval remains a separate release gate.
    """
    root = Path(__file__).parents[1]
    sources = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    native_root = Path(next(iter(verifiers.__path__)))
    sources.update(
        {
            "native_runtime/" + str(path.relative_to(native_root)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(native_root.rglob("*.py"))
        }
    )
    lock = root.parents[1] / "uv.lock"
    if lock.exists():
        sources["dependency-lock/uv.lock"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "benchmark_scorer_digest": scorer_fingerprint(),
        "native_source_digest": native_source_digest,
        "source_digests": sources,
        "configuration_json": canonical_json(configuration),
        "runtime": {"python": platform.python_version(), "pydantic": pydantic.__version__},
    }
    return RedesignRevision.model_validate({**payload, "digest": revision_digest(payload)})
