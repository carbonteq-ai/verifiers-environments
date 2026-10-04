"""Strict JSON loading and packaged catalog selection; never evaluate a task."""

import hashlib
import json
import re
import weakref
from functools import lru_cache
from importlib.resources import files

from .models import ContractSpec


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key:" + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite_json_constant:" + value)


def _decode(raw: bytes | str):
    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def load_contract(raw: bytes | str) -> ContractSpec:
    # Admitted contracts are deeply immutable, so equal bytes share one
    # validation; scoring re-admits the same manifest once per assessment.
    if isinstance(raw, (bytes, str)):
        return _admitted(raw)
    return ContractSpec.model_validate(_decode(raw))


@lru_cache(maxsize=32)
def _admitted(raw: bytes | str) -> ContractSpec:
    return ContractSpec.model_validate(_decode(raw))


_DIGESTS: dict[int, tuple[weakref.ref, str]] = {}


def canonical_contract_digest(contract: ContractSpec) -> str:
    key = id(contract)
    cached = _DIGESTS.get(key)
    if cached is not None and cached[0]() is contract:
        return cached[1]
    digest = _canonical_digest(contract)

    def forget(ref, key=key):
        if _DIGESTS.get(key, (None,))[0] is ref:
            del _DIGESTS[key]

    _DIGESTS[key] = (weakref.ref(contract, forget), digest)
    return digest


def _canonical_digest(contract: ContractSpec) -> str:
    serialized = json.dumps(
        contract.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _catalog() -> dict[str, str]:
    package = files("automationbench_v1.contracts")
    catalog = _decode(package.joinpath("catalog.json").read_bytes())
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"schema_version", "tasks"}
        or type(catalog.get("schema_version")) is not int
        or catalog["schema_version"] != 1
        or not isinstance(catalog.get("tasks"), dict)
    ):
        raise ValueError("task_catalog_schema_unresolved")
    for identity, path in catalog["tasks"].items():
        if (
            not isinstance(identity, str)
            or not identity
            or not isinstance(path, str)
            or not re.fullmatch(r"tasks/[a-z0-9][a-z0-9_-]*\.json", path)
        ):
            raise ValueError("task_catalog_path_unresolved")
    return catalog["tasks"]


def supported_tasks() -> tuple[str, ...]:
    """Validated packaged selections, without evaluating or importing task code."""
    return tuple(sorted(_catalog()))


def load_task_contract(task_name: str) -> ContractSpec:
    if not isinstance(task_name, str) or not task_name:
        raise ValueError("task_catalog_identity_required")
    path = _catalog().get(task_name)
    if path is None:
        raise ValueError("task_manifest_unregistered:" + task_name)
    contract = load_contract(files("automationbench_v1.contracts").joinpath(path).read_bytes())
    # Packaged policy is accepted only with public authority, rather than
    # relying on audit prose or a recorded final outcome to define correctness.
    # Standalone load_contract remains available for explicit test proposals.
    if not contract.bindings or any(
        binding.path[:2] not in {
            ("task_evidence", "prompt"), ("task_evidence", "initial"),
        }
        for binding in contract.bindings
    ):
        raise ValueError("installed_manifest_requires_public_authority_bindings")
    return contract
