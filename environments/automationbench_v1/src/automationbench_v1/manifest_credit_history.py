"""A consumed native episode ledger belongs to one manifest revision.

Fresh offline reward redesign uses a separate replay ledger. This boundary
does not infer semantic equivalence between renamed checks or policy families.
"""

import json
import re

_TOP_LEVEL_RULES = {
    "automationbench.manifest_verified_transition_once",
    "automationbench.manifest_per_effect_negative",
}
_CONSUMPTION_RULES = {
    "automationbench.manifest_summary_action_negative_once",
    "automationbench.manifest_required_effect_once",
    "automationbench.manifest_retained_completion_once",
    "automationbench.manifest_created_completion_once",
    "automationbench.manifest_record_retained_completion_once",
}


def assert_manifest_credit_revision(source, prior_assignments, contract_digest):
    """Valid partial contributions freeze the revision; empty attempts do not."""
    for assignment in prior_assignments:
        request, rule = assignment.request, assignment.request.rule
        if request.source.episode_id != source.episode_id:
            continue
        if rule.rule_id not in _TOP_LEVEL_RULES | _CONSUMPTION_RULES:
            continue
        if not any(part.status == "valid" for part in assignment.contributions):
            continue
        try:
            config = json.loads(rule.configuration_json)
        except (ValueError, TypeError) as error:
            raise ValueError("manifest_consumed_credit_revision_unavailable") from error
        if not isinstance(config, dict):
            raise ValueError("manifest_consumed_credit_revision_unavailable")  # noqa: TRY004 - invalid stored JSON value
        identity = config if rule.rule_id in _TOP_LEVEL_RULES else config.get("consumption")
        old = identity.get("contract_digest") if isinstance(identity, dict) else None
        if type(old) is not str or re.fullmatch(r"[0-9a-f]{64}", old) is None:
            raise ValueError("manifest_consumed_credit_revision_unavailable")
        if old != contract_digest:
            raise ValueError("manifest_consumed_credit_requires_fresh_revision_ledger")
