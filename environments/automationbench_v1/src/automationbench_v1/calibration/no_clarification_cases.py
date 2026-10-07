"""Fixed no-clarification preparation profile, sharing factual case carriers."""

from collections.abc import Mapping
from typing import Literal

from ..contracts.summary_policy import SummaryAssessor
from .summary_cases import (
    _CLARIFICATION,
    FrozenSummaryReplay,
    PreparedSummaryCase,
    SummaryCaseSpec,
    _load_replay,
    _prepare_case,
    _validate_prepared_case,
)


def load_no_clarification_replay(
    document: Mapping,
    *,
    policy_profile: Literal["no_clarification@1", "no_clarification@2"] = _CLARIFICATION,
) -> FrozenSummaryReplay:
    return _load_replay(document, profile=policy_profile)


def prepare_no_clarification_case(
    baseline: FrozenSummaryReplay,
    spec: SummaryCaseSpec,
    *,
    assessor: SummaryAssessor | None = None,
    policy_profile: Literal["no_clarification@1", "no_clarification@2"] = _CLARIFICATION,
) -> PreparedSummaryCase:
    return _prepare_case(baseline, spec, assessor=assessor, profile=policy_profile)


def prepare_no_clarification_cases(
    document: Mapping,
    *,
    assessor: SummaryAssessor | None = None,
    policy_profile: Literal["no_clarification@1", "no_clarification@2"] = _CLARIFICATION,
) -> tuple[PreparedSummaryCase, ...]:
    baseline = load_no_clarification_replay(document, policy_profile=policy_profile)
    return tuple(
        prepare_no_clarification_case(
            baseline,
            SummaryCaseSpec.model_validate(spec),
            assessor=assessor,
            policy_profile=policy_profile,
        )
        for spec in document["cases"]
    )


def validate_prepared_no_clarification_case(
    prepared: PreparedSummaryCase,
    *,
    policy_profile: Literal["no_clarification@1", "no_clarification@2"] = _CLARIFICATION,
) -> PreparedSummaryCase:
    return _validate_prepared_case(prepared, profile=policy_profile)
