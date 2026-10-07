"""Manifest occurrence goals, conservative baselines and once-per-obligation credit."""

import copy
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from test_manifest_guards import comparison, create, declaration, field, initial, literal, text
from test_notification_evidence import run_operations, zapier

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.effects import EffectSource, capture_effects
from automationbench_v1.contracts.obligations import (
    ObligationCheck,
    evaluate_obligations,
    plan_obligation_instances,
    select_obligation_credit,
)
from automationbench_v1.contracts.tables import TableSource, capture_table


def obligation():
    guard = declaration()
    return {
        "check_id": "required-provision",
        "signal_id": "access.required_effect",
        "role": "goal",
        "operator": "effects.required_when@1",
        "population": "queue",
        "source": "creates",
        "lookups": guard["lookups"],
        "required_when": {
            "op": "all",
            "args": [
                comparison(
                    "eq",
                    field("request", "Status", domain="string", allowed=["Pending", "Processed"]),
                    literal("Pending"),
                ),
                comparison("gte", field("manager", "Rank", domain="integer"), literal(3)),
            ],
        },
        "initially_satisfied_when": comparison(
            "eq", field("request", "Fulfilled", domain="boolean"), literal(True)
        ),
        "effect_match": guard["effect_match"],
    }


def world(*, fulfilled=False, rank=4, status="Pending"):
    result = initial(rank=rank, status=status)
    result["google_sheets"]["rows"][0]["cells"]["Fulfilled"] = fulfilled
    return result


def inputs(material):
    sources = {
        name: TableSource(
            path=("task_evidence", "initial", "google_sheets"),
            spreadsheet_id="sheet",
            worksheet_id=name,
            key_fields=("Email",),
            required_fields=("Manager", "Status") if name == "queue" else ("Rank",),
        )
        for name in ("queue", "directory")
    }
    populations = {name: capture_table(material, source) for name, source in sources.items()}
    effect_source = EffectSource(adapter="asana.actions@1", kind="create_task")
    effects = capture_effects(material, effect_source)
    return populations, sources, effects, effect_source


def evaluate(material, raw=None, *, evidence=None):
    populations, sources, effects, effect_source = inputs(material)
    return evaluate_obligations(
        material,
        ObligationCheck.model_validate(raw or obligation()),
        populations,
        effects if evidence is None else evidence,
        effect_source=effect_source,
        population_sources=sources,
    )


def test_required_qualified_occurrence_has_separate_positive_action_selection():
    result = evaluate(run_operations(world(), [create()]))
    finding = result.findings[0]
    assert finding.status == "valid" and finding.value == 1 and finding.required is True
    assert finding.initially_satisfied is False and result.scope_complete
    assert finding.witnesses[0].occurrence == "execution-0"
    selected = select_obligation_credit(result)
    assert len(selected) == 1 and selected[0].value == 1
    assert selected[0].instance_key == finding.instance_key
    assert selected[0].effect_id == finding.witnesses[0].effect_id


def new_occurrence():
    raw = obligation() | {"semantics": "new_occurrence"}
    del raw["initially_satisfied_when"]
    return raw


def test_derived_baseline_observes_initial_field_and_rejects_effect_context():
    expression = {"op": "eq", "left": {"kind": "derived", "expression": {
        "kind": "input", "format": "number", "path": ["request", "Amount"]}},
        "right": {"kind": "derived", "expression": {"kind": "input", "format": "number", "literal": 0}}}
    raw = obligation() | {"initially_satisfied_when": expression}
    check = ObligationCheck.model_validate(raw)
    assert check.initially_satisfied_when is not None
    for key in ("required_when", "initially_satisfied_when"):
        changed = copy.deepcopy(expression)
        changed["left"]["expression"]["path"] = ["effect", "Amount"]
        with pytest.raises(ValueError, match="predicate_context_unknown"):
            ObligationCheck.model_validate(obligation() | {key: changed})


def test_copied_derived_boolean_index_is_rejected_before_json_normalization():
    from automationbench_v1.contracts.predicates import Comparison, DerivedValue

    raw = {"op": "eq", "left": {"kind": "derived", "expression": {
        "kind": "input", "format": "number", "path": ["request", "arr", 1]}},
        "right": {"kind": "derived", "expression": {"kind": "input", "format": "number", "literal": 0}}}
    check = ObligationCheck.model_validate(obligation() | {"required_when": raw})
    assert isinstance(check.required_when, Comparison)
    assert isinstance(check.required_when.left, DerivedValue)
    expression = check.required_when.left.expression.model_copy(update={"path": ("request", "arr", True)})
    left = check.required_when.left.model_copy(update={"expression": expression})
    copied = check.required_when.model_copy(update={"left": left})
    with pytest.raises(ValueError):
        ObligationCheck.model_validate(obligation() | {"required_when": copied})


@pytest.mark.parametrize("fulfilled", [False, True, None])
def test_explicit_new_occurrence_requires_fresh_effect_without_fabricating_baseline(fulfilled):
    result = evaluate(
        run_operations(world(fulfilled=fulfilled), [create(), create()]), new_occurrence()
    )
    finding = result.findings[0]
    assert result.semantics == "new_occurrence"
    assert finding.value == 1 and finding.initially_satisfied is None
    assert finding.baseline_reason.endswith("not_applicable")
    selected = select_obligation_credit(result)
    assert len(selected) == 1 and selected[0].occurrence == "execution-0"
    assert select_obligation_credit(result, consumed={selected[0].instance_key}) == ()


def test_new_occurrence_does_not_accept_initial_discharge_predicate():
    with pytest.raises(ValueError, match="no_initial_discharge"):
        ObligationCheck.model_validate(obligation() | {"semantics": "new_occurrence"})


def test_new_occurrence_absence_needs_closed_inventory_even_if_initially_fulfilled():
    material = run_operations(world(fulfilled=True), [create(project="other-project")])
    result = evaluate(material, new_occurrence())
    assert result.findings[0].value == 0 and select_obligation_credit(result) == ()
    material["state_write_receipts"] = []
    assert evaluate(material, new_occurrence()).findings[0].value is None


@pytest.mark.parametrize("root", ["effect", "manager", "future", "missing"])
def test_lookup_keys_require_acyclic_initial_context(root):
    raw = obligation()
    key = next(iter(raw["lookups"][0]["keys"]))
    raw["lookups"][0]["keys"][key]["path"] = [root, "Email"]
    with pytest.raises(ValueError, match="lookup_context_unavailable"):
        ObligationCheck.model_validate(raw)


def test_repeated_calls_credit_once_and_explicit_consumption_survives_rescoring():
    material = run_operations(world(), [create(), create()])
    first = evaluate(material)
    assert len(first.findings[0].witnesses) == 2
    selected = select_obligation_credit(first)
    assert len(selected) == 1 and selected[0].occurrence == "execution-0"
    assert (
        select_obligation_credit(
            evaluate(json.loads(canonical_json(material))), consumed={selected[0].instance_key}
        )
        == ()
    )
    assert asdict(first) == asdict(evaluate(material))


def test_identical_effect_fact_repetition_does_not_multiply_witnesses():
    material = run_operations(world(), [create()])
    _, _, evidence, _ = inputs(material)
    result = evaluate(material, evidence=replace(evidence, effects=evidence.effects * 2))
    assert len(result.findings[0].witnesses) == len(select_obligation_credit(result)) == 1
    changed = replace(evidence.effects[0], params_json='{"name":"changed"}')
    with pytest.raises(ValueError, match="identity_conflict"):
        evaluate(material, evidence=replace(evidence, effects=(evidence.effects[0], changed)))


def test_missing_match_is_zero_only_with_known_baseline_and_closed_scope():
    material = run_operations(world(), [create(project="other-project")])
    result = evaluate(material)
    assert result.scope_complete and result.findings[0].value == 0
    assert select_obligation_credit(result) == ()
    material["state_write_receipts"] = []
    unknown = evaluate(material)
    assert unknown.findings[0].value is None and not unknown.scope_complete


def test_qualified_empty_selected_effect_inventory_proves_missing_required_occurrence():
    from automationbench.tools.zapier.asana.actions import asana_add_task_to_section

    operation = zapier(
        "asana_add_task_to_section",
        {
            "task_id": "existing",
            "workspace": "workspace",
            "projects": "project-access",
            "section": "section",
        },
        lambda state: asana_add_task_to_section(
            state,
            task_id="existing",
            workspace="workspace",
            projects="project-access",
            section="section",
        ),
    )
    material = run_operations(world(), [operation])
    _, _, evidence, _ = inputs(material)
    assert evidence.complete and evidence.effects == ()
    result = evaluate(material)
    assert result.findings[0].value == 0 and select_obligation_credit(result) == ()


@pytest.mark.parametrize("baseline", ["omitted", "missing", "wrong-type"])
def test_unknown_baseline_retains_observed_outcome_without_action_credit(baseline):
    before = world()
    raw = obligation()
    if baseline == "omitted":
        raw.pop("initially_satisfied_when")
    elif baseline == "missing":
        before["google_sheets"]["rows"][0]["cells"].pop("Fulfilled")
    else:
        before["google_sheets"]["rows"][0]["cells"]["Fulfilled"] = "False"
    result = evaluate(run_operations(before, [create()]), raw)
    assert result.findings[0].value == 1 and result.findings[0].initially_satisfied is None
    assert select_obligation_credit(result) == ()


def test_unknown_baseline_does_not_turn_missing_effect_into_zero():
    raw = obligation()
    raw.pop("initially_satisfied_when")
    result = evaluate(run_operations(world(), [create(project="other")]), raw)
    assert result.scope_complete and result.findings[0].value is None
    assert result.findings[0].reason == "obligation_baseline_unavailable"


def test_literal_baseline_cannot_masquerade_as_initial_evidence():
    raw = obligation()
    raw["initially_satisfied_when"] = comparison("eq", literal(False), literal(True))
    with pytest.raises(ValueError, match="baseline_requires_observed"):
        ObligationCheck.model_validate(raw)
    raw["initially_satisfied_when"] = {
        "op": "all",
        "args": [raw["initially_satisfied_when"], obligation()["initially_satisfied_when"]],
    }
    with pytest.raises(ValueError, match="baseline_requires_observed"):
        ObligationCheck.model_validate(raw)


def test_initial_satisfaction_discharges_obligation_without_new_effect_credit():
    result = evaluate(run_operations(world(fulfilled=True), [create(project="other")]))
    finding = result.findings[0]
    assert finding.value == 1 and finding.initially_satisfied is True and not finding.witnesses
    assert select_obligation_credit(result) == ()


def test_break_and_restore_cannot_reward_an_initially_satisfied_obligation():
    def break_initial(state):
        state.google_sheets.rows[0].cells["Fulfilled"] = False
        return {"success": True}

    material = run_operations(
        world(fulfilled=True), [zapier("manufactured_break", {}, break_initial), create()]
    )
    result = evaluate(material)
    assert result.findings[0].value == 1 and result.findings[0].initially_satisfied is True
    assert select_obligation_credit(result) == ()


@pytest.mark.parametrize("case", ["not-required", "unknown-policy"])
def test_policy_false_is_inapplicable_and_unknown_is_not_invented(case):
    before = world(rank=2)
    if case == "unknown-policy":
        before["google_sheets"]["rows"][1]["cells"]["Rank"] = None
    result = evaluate(run_operations(before, [create()]))
    finding = result.findings[0]
    assert finding.value is None
    assert finding.status == ("inapplicable" if case == "not-required" else "abstained")
    assert select_obligation_credit(result) == ()


@pytest.mark.parametrize("recipient", ["person@example.com", "other@example.com"])
def test_native_initial_record_population_and_gmail_send_need_no_sheet_adapter(recipient):
    from test_manifest_notification_effects import send

    from automationbench_v1.contracts.notification_effects import (
        NotificationEffectSource,
        capture_notification_effects,
    )
    from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population

    before = {
        "gmail": {
            "messages": [
                {
                    "id": "incoming-1",
                    "from_": "person@example.com",
                    "to": ["service@example.com"],
                    "subject": "Request",
                }
            ],
            "drafts": [],
        }
    }
    material = run_operations(before, [send(to=recipient)])
    population_source = InitialCollectionSource(
        path=("task_evidence", "initial", "gmail", "messages"),
        fields={"Email": ("from_",), "Subject": ("subject",)},
        key_fields=("Email",),
    )
    population = capture_population(material, population_source)
    effect_source = NotificationEffectSource()
    raw = new_occurrence() | {
        "lookups": [],
        "required_when": comparison(
            "eq", field("request", "Subject", domain="string"), literal("Request")
        ),
        "effect_match": comparison(
            "in", field("request", "Email", domain="string"), field("effect", "to", domain="sequence")
        ),
    }
    result = evaluate_obligations(
        material,
        ObligationCheck.model_validate(raw),
        {"queue": population},
        capture_notification_effects(material, effect_source),
        effect_source=effect_source,
        population_sources={"queue": population_source},
    )
    assert result.findings[0].candidate_identity[-1] == "incoming-1"
    assert result.findings[0].value == (1 if recipient == "person@example.com" else 0)
    assert len(select_obligation_credit(result)) == (1 if recipient == "person@example.com" else 0)


@pytest.mark.parametrize("competitor", ["known-match", "unknown-match"])
def test_ambiguous_candidate_matching_blocks_positive_attribution(competitor):
    before = world()
    row = copy.deepcopy(before["google_sheets"]["rows"][0])
    row["row_id"] = 2
    row["cells"]["Email"] = "other@example.com"
    before["google_sheets"]["rows"].append(row)
    raw = obligation()
    if competitor == "known-match":
        raw["effect_match"] = comparison(
            "eq", field("effect", "project", domain="string"), literal("project-access")
        )
    else:
        # Both identities are available; only the competing match value is unknown.
        before["google_sheets"]["rows"][0]["cells"]["Target"] = "Provision person@example.com"
        raw["effect_match"] = comparison(
            "eq",
            field("effect", "name", domain="string"),
            field("request", "Target", domain="string"),
        )
    result = evaluate(run_operations(before, [create()]), raw)
    assert all(finding.value is None for finding in result.findings)
    assert select_obligation_credit(result) == ()


def test_unrelated_duplicate_identity_preserves_independent_positive_witness():
    before = world()
    row = copy.deepcopy(before["google_sheets"]["rows"][0])
    row["row_id"] = 2
    row["cells"]["Email"] = "unrelated@example.com"
    before["google_sheets"]["rows"].extend([row, copy.deepcopy(row)])
    result = evaluate(run_operations(before, [create()]))
    assert not result.scope_complete and len(result.findings) == 2
    assert len(select_obligation_credit(result)) == 1
    assert result.findings[1].value is None


def test_candidate_identity_survives_reordering_population_growth_and_new_effects():
    before = world()
    first = evaluate(run_operations(before, [create()]))
    row = copy.deepcopy(before["google_sheets"]["rows"][0])
    row["row_id"] = 55
    row["cells"]["Email"] = "new@example.com"
    before["google_sheets"]["rows"].insert(0, row)
    before["google_sheets"]["rows"].reverse()
    later = evaluate(run_operations(before, [create(), create("new@example.com")]))
    same = next(
        finding
        for finding in later.findings
        if finding.candidate_identity == first.findings[0].candidate_identity
    )
    assert same.instance_key == first.findings[0].instance_key
    selected = select_obligation_credit(later, consumed={same.instance_key})
    assert len(selected) == 1 and selected[0].instance_key != same.instance_key


@pytest.mark.parametrize("later", ["missing-ack", "delete"])
def test_occurrence_goal_survives_later_gap_or_deletion_without_claiming_terminal_state(later):
    def erase(state):
        state.asana.actions["create_task"] = []
        return {"success": True}

    operations = (
        [create(), create()]
        if later == "missing-ack"
        else [create(), zapier("manufactured_delete", {}, erase)]
    )
    material = run_operations(world(), operations)
    if later == "missing-ack":
        material["state_write_receipts"] = material["state_write_receipts"][:1]
    result = evaluate(material)
    assert not result.scope_complete and result.findings[0].value == 1
    assert select_obligation_credit(result)[0].occurrence == "execution-0"
    raw = obligation() | {"semantics": "terminal_state"}
    with pytest.raises(ValueError):
        ObligationCheck.model_validate(raw)


@pytest.mark.parametrize("mode", ["empty", "missing"])
def test_zero_candidates_preserve_inventory_status_without_whole_task_success(mode):
    before = world()
    before["google_sheets"]["rows"] = before["google_sheets"]["rows"][1:]
    material = run_operations(before, [create()])
    if mode == "missing":
        material["task_evidence"]["initial"]["google_sheets"].pop("rows")
    result = evaluate(material)
    assert result.findings == () and select_obligation_credit(result) == ()
    assert result.reason == (
        "obligation_population_empty" if mode == "empty" else "obligation_population_unavailable"
    )
    assert result.scope_complete is (mode == "empty")


def test_budget_bounds_candidate_inventory_even_with_no_effects():
    material = run_operations(world(), [create(), create()])
    raw = obligation() | {"max_instances": 1}
    result = evaluate(material, raw)
    assert result.findings == () and not result.scope_complete
    assert result.reason == "obligation_instance_budget_exceeded"
    populations, _, effects, _ = inputs(material)
    check = ObligationCheck.model_validate(obligation())
    cases, potential = plan_obligation_instances(
        check, populations["queue"], replace(effects, effects=())
    )
    assert len(cases) == potential == 1


@pytest.mark.parametrize(
    "tamper", ["source", "selector", "population-selector", "lookup-keys", "final-baseline"]
)
def test_captured_evidence_and_initial_policy_scope_are_strictly_bound(tamper):
    material = run_operations(world(), [create()])
    populations, sources, effects, effect_source = inputs(material)
    raw = obligation()
    if tamper == "source":
        material = copy.deepcopy(material)
        material["task_evidence"]["initial"]["google_sheets"]["rows"][0]["cells"]["Fulfilled"] = (
            True
        )
    elif tamper == "selector":
        effect_source = EffectSource(adapter="asana.actions@1", kind="add_task_to_section")
    elif tamper == "population-selector":
        sources["queue"] = sources["queue"].model_copy(update={"key_fields": ("Manager",)})
    elif tamper == "lookup-keys":
        raw["lookups"][0]["keys"] = {"Other": field("request", "Manager", domain="string")}
    else:
        sources["queue"] = sources["queue"].model_copy(
            update={"path": ("task_evidence", "final", "google_sheets")}
        )
        populations["queue"] = capture_table(material, sources["queue"])
    with pytest.raises(ValueError):
        evaluate_obligations(
            material,
            ObligationCheck.model_validate(raw),
            populations,
            effects,
            effect_source=effect_source,
            population_sources=sources,
        )


def test_real_hash_bound_luna_access_occurrences_do_not_invent_missing_baseline_credit():
    index = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not index.exists():
        pytest.skip("retained development source index unavailable")
    binding = next(
        item["source_binding"]
        for item in json.loads(index.read_text())["tasks"]
        if item["task_name"] == "operations.access_request_validation"
    )
    path = Path(binding["source_episode_path"])
    raw_episode = path.read_bytes()
    assert hashlib.sha256(raw_episode).hexdigest() == binding["source_episode_sha256"]
    episode = json.loads(raw_episode)
    trace = episode["traces"][0]
    material = {
        "task_evidence": {
            "initial": episode["task"]["data"]["initial_state"],
            "final": trace["info"]["automationbench"]["end_state"],
            "complete": trace["is_completed"],
        },
        "tool_execution_events": trace["tool_execution_events"],
        "state_write_receipts": trace["state_write_receipts"],
    }
    source = TableSource(
        path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="ss_access_requests",
        worksheet_id="ws_queue",
        key_fields=("Email",),
        required_fields=("Status", "Requestor", "Requested Level", "Department"),
    )
    raw = obligation()
    raw["lookups"] = []
    raw.pop("initially_satisfied_when")
    raw["required_when"] = comparison(
        "eq",
        field("request", "Status", domain="string", allowed=["Pending", "Processed"]),
        literal("Pending"),
    )
    raw["effect_match"] = comparison(
        "eq",
        field("effect", "name", domain="string"),
        text(
            literal("IT provisioning: "),
            field("request", "Requestor", domain="string"),
            literal(" — "),
            field("request", "Requested Level", domain="string"),
            literal(" — "),
            field("request", "Department", domain="string"),
        ),
    )
    effect_source = EffectSource(adapter="asana.actions@1", kind="create_task")
    result = evaluate_obligations(
        material,
        ObligationCheck.model_validate(raw),
        {"queue": capture_table(material, source)},
        capture_effects(material, effect_source),
        effect_source=effect_source,
        population_sources={"queue": source},
    )
    assert sum(finding.value == 1 for finding in result.findings) == 3
    assert not result.scope_complete and select_obligation_credit(result) == ()
    assert path.read_bytes() == raw_episode
