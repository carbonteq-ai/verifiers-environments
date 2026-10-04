"""Read-only official replay under an explicitly selected local source/runtime.

Composition must approve the binding independently. Neither a hash nor a binding
embedded in an input artifact authorizes execution. Archive contents are checked,
never extracted or executed; the only entry point is the fixed local verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..capture import canonical_json
from .inventory import content_digest

_PACKAGES = {
    "automationbench": "automationbench",
    "automationbench_environment": "automationbench_v1",
    "verifiers": "verifiers",
}
_SCRIPT = r"""
import hashlib,json,platform,sys
from pathlib import Path
import pydantic
from automationbench_v1.calibration.models import CalibrationManifest
from automationbench_v1.calibration.inventory import load_inventory
from automationbench_v1.calibration.journal import AttemptEvent,AttemptJournal
from automationbench_v1.calibration.verify import verify_retained,scorer_fingerprint
payload=json.load(sys.stdin)
manifest=CalibrationManifest.model_validate_json(Path(payload['manifest']).read_bytes())
if platform.python_version()!=manifest.source_identity['python'] or pydantic.__version__!=manifest.source_identity['pydantic']:
    raise ValueError('frozen validation runtime differs')
for key,module in payload['modules'].items():
    loaded=__import__(module)
    if str(Path(loaded.__file__).resolve().parent)!=payload['roots'][key]:
        raise ValueError('frozen import root differs')
inventory=load_inventory(Path(payload['inventory']))
manifest.validate_inventory(inventory)
rows=[AttemptEvent.model_validate_json(line) for line in bytes.fromhex(payload['journal_hex']).splitlines()]
class ReadOnlyJournal(AttemptJournal):
    def __init__(self):
        self.manifest=manifest
        self.events=[]
        self.latest={}
        for row in rows:
            self._accept(row)
ReadOnlyJournal()
selected=[row for row in rows if row.episode_path==payload['episode']]
if len(selected)!=1:
    raise ValueError('original terminal occurrence ambiguous')
attempt=selected[0]
task=next(row for row in inventory.tasks if row.task_name==attempt.task_name)
report=verify_retained(Path(payload['episode']),task,attempt,manifest)
if 'assertion_results' not in report or report['reason'] not in (None,'assertions_not_fully_satisfied'):
    raise ValueError('original replay unavailable: '+str(report['reason']))
print(json.dumps({'report':report,'python':platform.python_version(),'pydantic':pydantic.__version__,'scorer':scorer_fingerprint()},sort_keys=True))
"""


class FrozenRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class FrozenVerifierBinding(FrozenRecord):
    """Trusted local execution selection supplied separately by composition."""

    interpreter: str
    interpreter_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_roots: dict[str, str]
    source_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_path: str
    archive_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    driver_revision: Literal["frozen-official-replay-v1"] = "frozen-official-replay-v1"
    driver_digest: str
    digest: str

    @model_validator(mode="after")
    def verify(self) -> Self:
        if set(self.package_roots) != set(_PACKAGES):
            raise ValueError("frozen verifier requires the three exact local package roots")
        if any(
            not Path(path).is_absolute()
            for path in (*self.package_roots.values(), self.interpreter, self.archive_path)
        ):
            raise ValueError("frozen verifier paths must be absolute")
        if self.driver_digest != hashlib.sha256(_SCRIPT.encode()).hexdigest():
            raise ValueError("frozen verifier driver provenance differs")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("frozen verifier binding digest mismatch")
        return self


class FrozenFile(FrozenRecord):
    name: Literal["inventory", "manifest", "journal", "episode", "outcome"]
    path: str
    digest: str
    prefix_bytes: int | None = Field(default=None, gt=0, strict=True)


class FrozenVerification(FrozenRecord):
    schema_version: Literal[1] = 1
    binding: FrozenVerifierBinding
    files: tuple[FrozenFile, ...]
    task_name: str
    task_digest: str
    manifest_digest: str
    attempt_id: str
    episode_digest: str
    outcome_digest: str
    scorer_digest: str
    python: str
    pydantic: str
    official_strict_score: float
    official_partial_credit: float
    all_declared_assertions_passed: bool
    assertion_results_json: str
    assertion_digest: str
    digest: str

    @model_validator(mode="after")
    def verify(self) -> Self:
        if len(self.files) != 5 or {item.name for item in self.files} != {
            "inventory",
            "manifest",
            "journal",
            "episode",
            "outcome",
        }:
            raise ValueError("frozen verification closure incomplete")
        for item in self.files:
            if not Path(item.path).is_absolute() or (
                item.prefix_bytes is not None and item.name != "journal"
            ):
                raise ValueError("frozen verification source reference invalid")
        assertions = json.loads(self.assertion_results_json)
        if (
            not isinstance(assertions, list)
            or canonical_json(assertions) != self.assertion_results_json
            or content_digest(assertions) != self.assertion_digest
        ):
            raise ValueError("frozen assertion bytes differ")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("frozen verification digest mismatch")
        return self


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_sources(binding: FrozenVerifierBinding, identity: dict) -> None:
    binding = FrozenVerifierBinding.model_validate_json(binding.model_dump_json())
    if (
        content_digest(identity) != binding.source_identity_digest
        or _sha(Path(binding.interpreter)) != binding.interpreter_digest
        or _sha(Path(binding.archive_path)) != binding.archive_digest
    ):
        raise ValueError("approved frozen source/archive/interpreter changed")
    expected = {}
    for name, package in identity["packages"].items():
        root = Path(binding.package_roots[name])
        files = package["files"]
        actual = {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".json"}
            and "__pycache__" not in path.parts
        }
        if actual != {name for name in files if not name.startswith("project/")}:
            raise ValueError("approved frozen source membership changed")
        if content_digest(files) != package["source_digest"]:
            raise ValueError("original source manifest digest mismatch")
        for relative, digest in files.items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("original source path escaped package")
            if relative.startswith("project/"):
                project = next(
                    parent for parent in root.parents if (parent / "pyproject.toml").exists()
                )
                path = project / relative.removeprefix("project/")
            else:
                path = root / relative
            if _sha(path) != digest:
                raise ValueError("approved local frozen source changed")
            expected[f"{name}/{relative}"] = digest
    with zipfile.ZipFile(binding.archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("frozen source archive membership differs")
        for name, digest in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError("frozen archived source differs")
    verifier = Path(binding.package_roots["automationbench_environment"]) / "calibration/verify.py"
    if _sha(verifier) != binding.verifier_digest:
        raise ValueError("approved verifier entry point changed")


def capture_frozen_verifier_binding(
    *,
    interpreter: Path,
    package_roots: dict[str, Path],
    source_archive: Path,
    source_identity: dict,
) -> FrozenVerifierBinding:
    """Capture candidates for independent approval; this function grants no trust."""
    roots = {name: str(path.resolve()) for name, path in package_roots.items()}
    body = {
        "interpreter": str(interpreter.absolute()),
        "interpreter_digest": _sha(interpreter),
        "package_roots": roots,
        "source_identity_digest": content_digest(source_identity),
        "archive_path": str(source_archive.resolve()),
        "archive_digest": _sha(source_archive),
        "verifier_digest": _sha(
            Path(roots["automationbench_environment"]) / "calibration/verify.py"
        ),
        "driver_revision": "frozen-official-replay-v1",
        "driver_digest": hashlib.sha256(_SCRIPT.encode()).hexdigest(),
    }
    binding = FrozenVerifierBinding.model_validate({**body, "digest": content_digest(body)})
    _check_sources(binding, source_identity)
    return binding


def build_frozen_verification(
    *,
    approved_binding: FrozenVerifierBinding,
    inventory_path: Path,
    manifest_path: Path,
    journal_path: Path,
    episode_path: Path,
) -> FrozenVerification:
    """Execute only the fixed verifier in independently approved local sources."""
    manifest = json.loads(manifest_path.read_bytes())
    _check_sources(approved_binding, manifest["source_identity"])
    episode_path = episode_path.resolve()
    raw = journal_path.read_bytes()
    prefix = b""
    terminal = None
    for line in raw.splitlines(keepends=True):
        prefix += line
        row = json.loads(line)
        if row.get("episode_path") == str(episode_path):
            terminal = row
            break
    if terminal is None or terminal["status"] != "retained" or not prefix.endswith(b"\n"):
        raise ValueError("frozen verification requires a committed retained terminal")
    paths = {
        "inventory": inventory_path,
        "manifest": manifest_path,
        "journal": journal_path,
        "episode": episode_path,
        "outcome": episode_path.with_name("outcome.json"),
    }
    files = tuple(
        FrozenFile(
            name=cast(Literal["inventory", "manifest", "journal", "episode", "outcome"], name),
            path=str(path.resolve()),
            digest=hashlib.sha256(prefix if name == "journal" else path.read_bytes()).hexdigest(),
            prefix_bytes=len(prefix) if name == "journal" else None,
        )
        for name, path in paths.items()
    )
    payload = {
        "inventory": str(inventory_path.resolve()),
        "manifest": str(manifest_path.resolve()),
        "episode": str(episode_path),
        "journal_hex": prefix.hex(),
        "roots": approved_binding.package_roots,
        "modules": _PACKAGES,
    }
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            dict.fromkeys(
                str(Path(root).parent) for root in approved_binding.package_roots.values()
            )
        ),
    }
    completed = subprocess.run(
        [approved_binding.interpreter, "-B", "-c", _SCRIPT],
        input=canonical_json(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
        cwd="/",
    )
    if completed.returncode:
        raise ValueError("frozen official replay failed: " + completed.stderr.splitlines()[-1])
    result = json.loads(completed.stdout)
    _check_sources(approved_binding, manifest["source_identity"])
    for reference in files:
        observed = Path(reference.path).read_bytes()
        if reference.prefix_bytes is not None:
            observed = observed[: reference.prefix_bytes]
        if hashlib.sha256(observed).hexdigest() != reference.digest:
            raise ValueError("original evidence changed during frozen replay")
    report = result["report"]
    assertions = report["assertion_results"]
    body = {
        "schema_version": 1,
        "binding": approved_binding.model_dump(mode="json"),
        "files": [item.model_dump(mode="json") for item in files],
        "task_name": terminal["task_name"],
        "task_digest": terminal["task_digest"],
        "manifest_digest": manifest["digest"],
        "attempt_id": report["attempt_id"],
        "episode_digest": report["episode_digest"],
        "outcome_digest": report["outcome_digest"],
        "scorer_digest": result["scorer"],
        "python": result["python"],
        "pydantic": result["pydantic"],
        "official_strict_score": report["official_strict_score"],
        "official_partial_credit": report["official_partial_credit"],
        "all_declared_assertions_passed": report["all_declared_assertions_passed"],
        "assertion_results_json": canonical_json(assertions),
        "assertion_digest": content_digest(assertions),
    }
    return FrozenVerification.model_validate({**body, "digest": content_digest(body)})


def validate_frozen_verification(
    verification: FrozenVerification, *, approved_binding: FrozenVerifierBinding
) -> None:
    """Integrity plus independent approved provenance and replay, not a result flag."""
    verification = FrozenVerification.model_validate_json(verification.model_dump_json())
    if verification.binding != approved_binding:
        raise ValueError("frozen verifier was not independently approved")
    refs = {item.name: item for item in verification.files}
    for reference in verification.files:
        raw = Path(reference.path).read_bytes()
        if reference.prefix_bytes is not None:
            raw = raw[: reference.prefix_bytes]
        if hashlib.sha256(raw).hexdigest() != reference.digest:
            raise ValueError("frozen original evidence changed")
    current = build_frozen_verification(
        approved_binding=approved_binding,
        inventory_path=Path(refs["inventory"].path),
        manifest_path=Path(refs["manifest"].path),
        journal_path=Path(refs["journal"].path),
        episode_path=Path(refs["episode"].path),
    )
    if current != verification:
        raise ValueError("frozen replay differs from retained verification")
