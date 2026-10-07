"""Created-object schema admission; semantic evidence is qualified separately."""

import copy
import json
from pathlib import Path

import pytest

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.engine import compile_contract
from automationbench_v1.contracts.models import CreditSpec

DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'jira-accessibility-draft.json'


@pytest.fixture
def raw():
    if not DRAFT.exists():
        pytest.skip('local public declaration unavailable')
    return json.loads(DRAFT.read_text())


def test_created_request_and_issue_schema_compile_with_explicit_credit_selection(raw):
    contract = load_contract(canonical_json(raw))
    compile_contract(contract)
    assert contract.credit[0].completion_selection == 'earliest'
    assert load_contract(canonical_json(contract.model_dump(mode='json'))) == contract


@pytest.mark.parametrize('variant,reason', [
    ('wrong-source', 'created_requires_issue_selector'),
    ('wrong-population', 'created_requires_authored_request_population'),
    ('missing-selection', 'created_completion_requires_explicit_selection'),
    ('wrong-selection', 'completion_selection'),
    ('wrong-goal-field', 'created_completion_goal_field_not_read'),
    ('duplicate-goal-field', 'created_completion_requires_explicit_selection'),
    ('wrong-credit-policy', 'goal_fields_only_for_retained_completion'),
    ('initial-baseline', 'Extra inputs'),
    ('occurrence-semantics', 'Extra inputs'),
])
def test_created_contract_rejects_mismatched_or_inferred_semantics(raw, variant, reason):
    data = copy.deepcopy(raw)
    if variant == 'wrong-source':
        data['sources']['issues'] = {'adapter': 'asana.actions@1', 'kind': 'create_task'}
    elif variant == 'wrong-population':
        data['checks'][0]['population'] = 'issues'
    elif variant == 'missing-selection':
        data['credit'][0].pop('completion_selection')
    elif variant == 'wrong-selection':
        data['credit'][0]['completion_selection'] = 'latest'
    elif variant == 'wrong-goal-field':
        data['credit'][0]['goal_fields'] = ['status']
    elif variant == 'duplicate-goal-field':
        data['credit'][0]['goal_fields'] = ['summary', 'summary']
    elif variant == 'wrong-credit-policy':
        data['credit'][0]['policy'] = 'required_effect_once@1'
    elif variant == 'initial-baseline':
        data['checks'][0]['initially_satisfied_when'] = data['checks'][0]['required_when']
    else:
        data['checks'][0]['semantics'] = 'occurrence'
    with pytest.raises(ValueError, match=reason):
        load_contract(canonical_json(data))


@pytest.mark.parametrize('policy', ['verified_transition_once@1', 'required_effect_once@1',
    'retained_completion_once@1', 'per_effect_negative@1'])
def test_old_credit_policies_reject_even_null_completion_selector(policy):
    raw = {'check': 'goal', 'policy': policy, 'channel': 'useful', 'completion_selection': None}
    with pytest.raises(ValueError, match='completion_selection_only_for_created_retained'):
        CreditSpec.model_validate(raw)


def test_old_credit_wires_do_not_gain_null_selection_field():
    raw = {'check': 'goal', 'policy': 'verified_transition_once@1', 'channel': 'useful'}
    assert CreditSpec.model_validate(raw).model_dump(mode='json') == {
        **raw, 'checks': []}
