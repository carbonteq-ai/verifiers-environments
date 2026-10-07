"""Reward identity changes without rewriting historical collection identity."""

import hashlib

import pytest
from pydantic import ValidationError

from automationbench_v1.calibration import reward_revision as module
from automationbench_v1.capture import canonical_json


@pytest.fixture
def sources(tmp_path, monkeypatch):
    package = tmp_path / "env" / "src" / "automationbench_v1"
    calibration = package / "calibration"
    calibration.mkdir(parents=True)
    (calibration / "reward_revision.py").write_text("# identity adapter\n")
    (package / "hr_rules.py").write_text("# rule version one\n")
    lock = tmp_path / "env" / "uv.lock"
    lock.write_text("version = 1\n")
    native = tmp_path / "native"
    native.mkdir()
    (native / "assessment.py").write_text("# native version one\n")
    monkeypatch.setattr(module, "__file__", str(calibration / "reward_revision.py"))
    monkeypatch.setattr(module.verifiers, "__path__", [str(native)])
    monkeypatch.setattr(module, "scorer_fingerprint", lambda: "a" * 64)
    return package, native, lock


def test_capture_binds_actual_rules_native_configuration_and_lock(sources):
    package, native, lock = sources
    configuration = {"goals": ["nda.sent"], "guard_revision": 1}
    original = module.capture_redesign_revision(configuration, "b" * 64)
    assert original.benchmark_scorer_digest == "a" * 64
    assert (
        original.source_digests["hr_rules.py"]
        == hashlib.sha256((package / "hr_rules.py").read_bytes()).hexdigest()
    )
    assert "native_runtime/assessment.py" in original.source_digests
    assert "dependency-lock/uv.lock" in original.source_digests
    assert original == module.capture_redesign_revision(configuration, "b" * 64)
    (package / "hr_rules.py").write_text("# changed guard\n")
    changed_rule = module.capture_redesign_revision(configuration, "b" * 64)
    assert changed_rule.digest != original.digest
    assert changed_rule.benchmark_scorer_digest == original.benchmark_scorer_digest
    (native / "assessment.py").write_text("# changed native assessment\n")
    changed_native = module.capture_redesign_revision(configuration, "b" * 64)
    assert changed_native.digest != changed_rule.digest
    lock.write_text("version = 2\n")
    changed_lock = module.capture_redesign_revision(configuration, "b" * 64)
    assert changed_lock.digest != changed_native.digest
    assert (
        module.capture_redesign_revision({**configuration, "guard_revision": 2}, "b" * 64).digest
        != changed_lock.digest
    )
    assert module.capture_redesign_revision(configuration, "c" * 64).digest != changed_lock.digest


def test_serialization_detects_nested_mutation(sources):
    revision = module.capture_redesign_revision({}, "b" * 64)
    revision.source_digests["hr_rules.py"] = "c" * 64
    with pytest.raises(ValidationError, match="identity changed"):
        module.RedesignRevision.model_validate_json(revision.model_dump_json())


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_digests", {}),
        ("source_digests", {"rule.py": "bad"}),
        ("source_digests", {"": "a" * 64}),
        ("configuration_json", "[]"),
        ("configuration_json", '{"b": 1, "a": 2}'),
        ("runtime", {"python": "3.13"}),
    ],
)
def test_resealed_invalid_identity_is_rejected(sources, field, value):
    body = module.capture_redesign_revision({}, "b" * 64).model_dump(
        mode="json", exclude={"digest"}
    )
    body[field] = value
    with pytest.raises(ValidationError):
        module.RedesignRevision.model_validate({**body, "digest": module.revision_digest(body)})


def test_configuration_key_order_does_not_change_identity(sources):
    first = module.capture_redesign_revision({"a": 1, "b": 2}, "b" * 64)
    second = module.capture_redesign_revision({"b": 2, "a": 1}, "b" * 64)
    assert first.digest == second.digest
    assert first.configuration_json == canonical_json({"a": 1, "b": 2})
