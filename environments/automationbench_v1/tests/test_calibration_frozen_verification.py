"""Actual offline native verifier subprocesses on synthetic local artifacts."""

import json

import pytest
from test_calibration_eligibility import make_reference

from automationbench_v1.calibration.eligibility import build_eligibility_proof
from automationbench_v1.calibration.frozen_verification import (
    FrozenVerification,
    validate_frozen_verification,
)
from automationbench_v1.calibration.inventory import content_digest


def test_score_preservation_optional_historical_policy_and_unforgeable_result(tmp_path):
    reference = make_reference(tmp_path / "reference", solved=False)
    kwargs = reference["kwargs"]
    proof = build_eligibility_proof(**kwargs)
    original = proof.frozen_verification
    assert original.official_strict_score == original.official_partial_credit == 0
    assert not original.all_declared_assertions_passed
    # Test-only independently supplied redesign policy qualifies its own checks;
    # it is not scientific approval of the synthetic claim or original task.
    assert proof.contract.admission_policy == "accepted_redesign"
    body = original.model_dump(mode="json", exclude={"digest"})
    body["official_strict_score"] = 1.0
    forged = FrozenVerification.model_validate({**body, "digest": content_digest(body)})
    with pytest.raises(ValueError, match="differs from retained"):
        validate_frozen_verification(forged, approved_binding=kwargs["approved_binding"])


def test_explicit_historical_full_policy_rejects_low_original_score(tmp_path):
    reference = make_reference(
        tmp_path / "reference", solved=False, admission_policy="historical_full_and_redesign"
    )
    with pytest.raises(ValueError, match="historical full-score"):
        build_eligibility_proof(**reference["kwargs"])


def test_archive_or_verifier_approval_change_rejected_before_execution(tmp_path, monkeypatch):
    from automationbench_v1.calibration import frozen_verification

    reference = make_reference(tmp_path / "reference")
    kwargs = reference["kwargs"]
    original = FrozenVerification.model_validate_json(
        kwargs["frozen_verification_path"].read_bytes()
    )
    binding = kwargs["approved_binding"]
    other = binding.model_dump(mode="json", exclude={"digest"})
    other["interpreter_digest"] = "0" * 64
    other = type(binding).model_validate({**other, "digest": content_digest(other)})
    called = []
    monkeypatch.setattr(frozen_verification.subprocess, "run", lambda *a, **k: called.append(a))
    with pytest.raises(ValueError, match="not independently approved"):
        validate_frozen_verification(original, approved_binding=other)
    archive = kwargs["approved_binding"].archive_path
    from pathlib import Path

    Path(archive).write_bytes(Path(archive).read_bytes() + b"changed")
    with pytest.raises(ValueError, match="archive/interpreter changed"):
        validate_frozen_verification(original, approved_binding=binding)
    assert not called


def test_original_journal_or_assertion_payload_tamper_rejected(tmp_path):
    reference = make_reference(tmp_path / "reference")
    kwargs = reference["kwargs"]
    original = FrozenVerification.model_validate_json(
        kwargs["frozen_verification_path"].read_bytes()
    )
    body = original.model_dump(mode="json", exclude={"digest"})
    body["assertion_results_json"] = json.dumps([])
    with pytest.raises(ValueError, match="assertion bytes"):
        FrozenVerification.model_validate({**body, "digest": content_digest(body)})
    journal = kwargs["journal_path"]
    journal.write_bytes(journal.read_bytes().replace(b'"retained"', b'"rejected"'))
    with pytest.raises(ValueError, match="original evidence changed"):
        validate_frozen_verification(original, approved_binding=kwargs["approved_binding"])
