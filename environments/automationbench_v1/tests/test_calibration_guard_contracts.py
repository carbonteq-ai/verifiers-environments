"""Policy inventory closure is distinct from numeric guard rewards."""

import pytest
import verifiers.v1 as vf

from automationbench_v1.calibration.eligibility import RequiredRewardCheck, TaskRewardContract
from automationbench_v1.calibration.inventory import content_digest


def _body(*, guard_keys=(), status="reviewed_closed", supplied_guards=()):
    checks = []
    for key, purpose in (
        ("goal", "goal"),
        ("coverage", "coverage"),
        *[(key, "guard") for key in supplied_guards],
    ):
        check = RequiredRewardCheck(
            key=key,
            purpose=purpose,
            signal=vf.SignalDefinition(
                signal_id=key, revision="1", semantics="other", description=key, units="indicator"
            ),
            producer_id="fixture",
            producer_revision="1",
            rubric_revision="1",
            subject_kind="trace",
            expected_value=1.0,
        )
        checks.append(check.model_dump(mode="json"))
    return {
        "schema_version": 2,
        "task_name": "fixture.task",
        "task_digest": "a" * 64,
        "policy_source_digest": "b" * 64,
        "admission_policy": "accepted_redesign",
        "guard_set": {
            "status": status,
            "check_keys": list(guard_keys),
            "policy_source_digest": "b" * 64,
            "scope": "task_specific",
            "review_revision": "review-1",
        },
        "checks": checks,
    }


def _contract(body):
    return TaskRewardContract.model_validate({**body, "digest": content_digest(body)})


def test_reviewed_empty_guard_set_requires_no_synthetic_reward():
    contract = _contract(_body())
    assert contract.guard_set.check_keys == ()
    assert {check.purpose for check in contract.checks} == {"goal", "coverage"}


@pytest.mark.parametrize("status", ["unreviewed", "unresolved"])
def test_empty_unreviewed_or_unresolved_inventory_cannot_admit(status):
    with pytest.raises(ValueError, match="not reviewed closed"):
        _contract(_body(status=status))


@pytest.mark.parametrize(
    "declared,supplied", [((), ("harm",)), (("harm",), ()), (("harm",), ("other",))]
)
def test_every_guard_matches_the_reviewed_inventory_exactly(declared, supplied):
    with pytest.raises(ValueError, match="differ from reviewed inventory"):
        _contract(_body(guard_keys=declared, supplied_guards=supplied))


def test_nonempty_closed_inventory_and_source_binding():
    body = _body(guard_keys=("harm",), supplied_guards=("harm",))
    assert _contract(body).guard_set.check_keys == ("harm",)
    body["guard_set"]["policy_source_digest"] = "c" * 64
    with pytest.raises(ValueError, match="policy source differs"):
        _contract(body)


def test_omitted_inventory_and_old_candidate_schema_fail_explicitly():
    body = _body()
    del body["guard_set"]
    with pytest.raises(ValueError, match="guard_set"):
        _contract(body)
    body = _body()
    body["schema_version"] = 1
    with pytest.raises(ValueError, match="schema_version"):
        _contract(body)
