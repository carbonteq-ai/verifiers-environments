"""Content identity and private snapshots of the actual loaded source packages."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import zipfile
from pathlib import Path

import pydantic
import verifiers

import automationbench
import automationbench_v1

from .inventory import content_digest


def source_identity(snapshot: Path | None = None) -> dict:
    packages = {
        "verifiers": Path(verifiers.__file__).resolve().parent,
        "automationbench_environment": Path(automationbench_v1.__file__).resolve().parent,
        "automationbench": Path(automationbench.__file__).resolve().parent,
    }
    identity: dict = {
        "python": platform.python_version(),
        "pydantic": pydantic.__version__,
        "sdk_version_required": "0.160.0",
        "packages": {},
    }
    retained: dict[str, bytes] = {}
    for name, package in packages.items():
        files = {
            str(path.relative_to(package)): path.read_bytes()
            for path in sorted(package.rglob("*"))
            if path.is_file()
            and path.suffix in {".py", ".json"}
            and "__pycache__" not in path.parts
        }
        for parent in package.parents:
            if (parent / "pyproject.toml").exists():
                for filename in ("pyproject.toml", "uv.lock"):
                    path = parent / filename
                    if path.exists():
                        files[f"project/{filename}"] = path.read_bytes()
                break
        hashes = {path: hashlib.sha256(raw).hexdigest() for path, raw in files.items()}
        revision = subprocess.run(
            ["git", "-C", str(package), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(package), "branch", "--show-current"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        identity["packages"][name] = {
            "git_revision": revision,
            "git_branch": branch,
            "files": hashes,
            "source_digest": content_digest(hashes),
        }
        retained.update({f"{name}/{path}": raw for path, raw in files.items()})
    if snapshot is not None:
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        # Source files and dependency manifests only: never host configuration/auth.
        with zipfile.ZipFile(snapshot, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, raw in sorted(retained.items()):
                archive.writestr(path, raw)
    return identity
