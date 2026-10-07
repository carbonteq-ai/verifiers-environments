"""Prepared challenge evidence, not semantic-label accuracy or model qualification."""

import asyncio
import base64
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError
from verifiers.v1.assessment_runtime import execute_assessment_plan

from automationbench_v1.calibration.no_clarification_cases import (
    load_no_clarification_replay,
    prepare_no_clarification_case,
    validate_prepared_no_clarification_case,
)
from automationbench_v1.calibration.summary_cases import (
    PreparedSummaryCase,
    SummaryCaseSpec,
    load_summary_replay,
    prepare_summary_case,
    validate_prepared_summary_case,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.invocation_inventory import capture_invocation_inventory
from automationbench_v1.contracts.no_clarification import NoClarificationCheck
from automationbench_v1.contracts.summary_policy import SummaryExclusionCheck
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_summary_assessments import assess_summary, summary_requests
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig

DOCUMENT = Path(
    "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/summary-semantic-case-preparation.json"
)


@pytest.fixture(scope="module")
def clarification_cases(tmp_path_factory):
    if not DOCUMENT.exists():
        pytest.skip("Reviewed baseline preparation document unavailable")
    document = json.loads(DOCUMENT.read_bytes())
    target = {"inventory": "assistant", "selector": "original_final"}
    insertion = {
        "kind": "insert_assistant_output",
        "output_alias": "earlier",
        "template": "original_final",
        "before": "contact_update",
        "text": "Which record should I update?",
    }
    inserted_target = {"inventory": "assistant", "selector": "earlier"}
    user_text = json.loads(Path(document["baseline"]["episode"]["path"]).read_bytes())["task"][
        "data"
    ]["prompt"][1]["content"]
    definitions = [
        ("actual", [], target),
        ("earlier", [insertion], inserted_target),
        (
            "duplicate",
            [insertion, {"kind": "duplicate_assistant_completion", "selector": "earlier"}],
            inserted_target,
        ),
        ("two", [insertion, {**insertion, "output_alias": "second"}], inserted_target),
        (
            "conflict",
            [
                insertion,
                {
                    "kind": "duplicate_assistant_completion",
                    "selector": "earlier",
                    "text": "Different completion",
                },
            ],
            None,
        ),
        (
            "empty",
            [
                {"kind": "remove_all_operations"},
                {"kind": "remove_assistant_output", "selector": "original_final"},
            ],
            None,
        ),
        (
            "variant",
            [
                {
                    "kind": "replace_user_request",
                    "prompt_index": 1,
                    "expected_text": user_text,
                    "text": "Update the Contact using the introduction, then send the requested scheduling question.",
                }
            ],
            target,
        ),
        (
            "send",
            [
                {
                    "kind": "replace_user_request",
                    "prompt_index": 1,
                    "expected_text": user_text,
                    "text": "Update the Contact using the introduction, then email Rachel to ask which meeting time works.",
                },
                {
                    "kind": "insert_operation",
                    "after": "contact_update",
                    "operation_alias": "send",
                    "outer_tool": "execute_tool",
                    "tool_name": "gmail_send_email",
                    "arguments": {
                        "to": "rachel.nguyen@ironclad.example.com",
                        "subject": "Scheduling",
                        "body": "Which meeting time works?",
                    },
                },
            ],
            {
                "inventory": "external",
                "operation_alias": "send",
                "service": "gmail",
                "collection": "messages",
                "record_id": None,
                "field": "body_plain",
            },
        ),
    ]
    reviews, specs = [], []
    for name, transforms, selected in definitions:
        output_alias = "review-" + name if selected is not None else None
        review = {
            "case_id": name,
            "provenance": "retained_actual_output"
            if not transforms
            else "manufactured_counterfactual",
            "output": {"output_id": output_alias} if selected is not None else None,
        }
        reviews.append(review)
        specs.append(
            {
                "case_id": name,
                "evaluation_case_sha256": hashlib.sha256(
                    canonical_json(review).encode()
                ).hexdigest(),
                "capture_mode": "retained_actual"
                if not transforms
                else "manufactured_counterfactual",
                "transforms": transforms,
                "target": selected,
                "evaluation_output_alias": output_alias,
            }
        )
    unsupported = {
        "case_id": "private",
        "provenance": "manufactured_counterfactual",
        "output": None,
    }
    reviews.append(unsupported)
    review_path = tmp_path_factory.mktemp("clarification-review") / "review.json"
    review_path.write_text(canonical_json({"cases": reviews}))
    document.update(
        policy_profile="no_clarification@1",
        additional_reviewed_tools=["gmail_send_email"],
        cases=specs,
        corpus={
            "path": str(review_path),
            "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        },
        unsupported_cases=[
            {
                "case_id": "private",
                "evaluation_case_sha256": hashlib.sha256(
                    canonical_json(unsupported).encode()
                ).hexdigest(),
                "reason": "No qualified private reasoning source transform",
            }
        ],
    )
    baseline = load_no_clarification_replay(document)
    cases = {
        spec["case_id"]: prepare_no_clarification_case(
            baseline, SummaryCaseSpec.model_validate(spec)
        )
        for spec in specs
    }
    return document, baseline, cases


def test_clarification_v2_requires_explicit_selection_and_binds_new_context(clarification_cases):
    document, _, cases = clarification_cases
    revised = copy.deepcopy(document)
    revised["policy_profile"] = "no_clarification@2"
    with pytest.raises(ValueError, match="policy_profile_changed"):
        load_no_clarification_replay(revised)
    baseline = load_no_clarification_replay(revised, policy_profile="no_clarification@2")
    prepared = prepare_no_clarification_case(
        baseline,
        SummaryCaseSpec.model_validate(revised["cases"][0]),
        policy_profile="no_clarification@2",
    )
    assert prepared.contract.checks[0].operator == "no_clarification@2"
    assert prepared.contract.revision == "2"
    assert prepared.source == cases["actual"].source
    assert prepared.context.context_digest != cases["actual"].context.context_digest
    assert (
        validate_prepared_no_clarification_case(prepared, policy_profile="no_clarification@2")
        == prepared
    )
    with pytest.raises(ValueError, match="policy_profile_changed"):
        validate_prepared_no_clarification_case(prepared)
    with pytest.raises(ValueError, match="policy_profile_changed"):
        validate_prepared_no_clarification_case(
            cases["actual"], policy_profile="no_clarification@2"
        )
    forged = prepared.model_copy(
        update={
            "contract": prepared.contract.model_copy(
                update={
                    "checks": (
                        prepared.contract.checks[0].model_copy(
                            update={"operator": "no_clarification@1"}
                        ),
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="contract_scope_changed"):
        validate_prepared_no_clarification_case(forged, policy_profile="no_clarification@2")


def test_clarification_profile_preserves_actual_source_and_rejects_cross_policy(
    clarification_cases, corpus
):
    document, baseline, cases = clarification_cases
    assert len(cases) == 8 and "private" not in cases
    for case in cases.values():
        assert isinstance(case.contract.checks[0], NoClarificationCheck)
        assert not case.contract.credit
        assert (
            validate_prepared_no_clarification_case(
                PreparedSummaryCase.model_validate_json(case.model_dump_json())
            )
            == case
        )
        with pytest.raises(ValueError):
            validate_prepared_summary_case(case)
    assert cases["actual"].source == baseline.source
    with pytest.raises(ValueError):
        load_summary_replay(document)
    with pytest.raises(ValueError):
        load_no_clarification_replay(corpus[0])
    with pytest.raises(ValueError):
        validate_prepared_no_clarification_case(corpus[2]["01a"])
    assert cases["actual"].context.check_digest != corpus[2]["01a"].context.check_digest


def test_inserted_requests_precede_original_action_without_replacing_final(clarification_cases):
    _, baseline, cases = clarification_cases
    original = json.loads(baseline.document_json)["selectors"]["original_final"]["expected_text"]
    for name, expected in (("earlier", 2), ("duplicate", 2), ("two", 3)):
        case = cases[name]
        outputs = [o for o in case.context.outputs if o.inventory == "assistant"]
        assert len(outputs) == expected and any(o.text == original for o in outputs)
        sdk = json.loads(
            base64.b64decode(safe(case)["task_evidence"]["authored_outputs"]["sdk_artifact_base64"])
        )
        events = sdk["events"]
        question_positions = [
            i
            for i, e in enumerate(events)
            if e.get("event", {}).get("params", {}).get("item", {}).get("text")
            == "Which record should I update?"
        ]
        action_position = next(
            i
            for i, e in enumerate(events)
            if e.get("event", {}).get("method") == "item/started"
            and e["event"]["params"]["item"].get("arguments", {}).get("tool_name")
            == "salesforce_contact_update"
        )
        assert question_positions and max(question_positions) < action_position
        assert case.context.assistant_closed and case.context.external_closed
        assert all(o.channel is None for o in outputs)  # Inherited unknown; no fabricated audience.
    assert not cases["conflict"].context.assistant_closed
    assert cases["conflict"].target_output_key is None


def test_empty_scope_is_real_zero_execution(clarification_cases):
    _, baseline, cases = clarification_cases
    empty = cases["empty"]
    assert not empty.context.outputs and not empty.context.invocations
    assert (
        empty.context.assistant_closed
        and empty.context.external_closed
        and empty.context.invocation_closed
    )
    assert safe(empty)["task_evidence"]["final"] == safe(empty)["task_evidence"]["initial"]
    assert (
        safe(empty)["task_evidence"]["initial"]
        == json.loads(baseline.source.source_json)["task_evidence"]["initial"]
    )
    assert (
        json.loads(empty.provenance_json)["zero_operation_identity_transition"][
            "observed_hydrated_world"
        ]
        is False
    )
    assert not safe(empty)["tool_execution_events"] and not safe(empty)["state_write_receipts"]


def test_reviewed_send_is_real_handler_output(clarification_cases):
    _, _, cases = clarification_cases
    send = cases["send"]
    target = next(o for o in send.context.outputs if o.output_key == send.target_output_key)
    fact = json.loads(target.fact_json)
    assert target.text == "Which meeting time works?" and fact["record_id"]
    final = safe(send)["task_evidence"]["final"]["gmail"]["messages"]
    persisted = next(row for row in final if row["id"] == fact["record_id"])
    assert persisted["body_plain"] == target.text
    assert "gmail_send_email" in json.loads(send.task_data_json)["zapier_tools"]
    assert any(
        "gmail_send_email" in key
        for key in json.loads(send.provenance_json)["handler_source_sha256"]
    )
    assert send.context.external_closed and send.context.invocation_closed
    assert (
        safe(send)["task_evidence"]["prompt"][0]
        == safe(cases["actual"])["task_evidence"]["prompt"][0]
    )
    assert (
        safe(send)["task_evidence"]["prompt"][1]
        != safe(cases["actual"])["task_evidence"]["prompt"][1]
    )


@pytest.mark.parametrize(
    "fault", ["profile", "operator", "context", "config", "target", "source", "tools"]
)
def test_clarification_prepared_substitution_rejected(clarification_cases, fault):
    case = clarification_cases[2]["earlier"]
    updates = {}
    if fault == "profile":
        document = json.loads(case.preparation_document_json)
        document["policy_profile"] = "summary_exclusions@1"
        updates["preparation_document_json"] = canonical_json(document)
    elif fault == "operator":
        contract = case.contract.model_dump(mode="json")
        contract["checks"][0]["operator"] = "summary_exclusions@1"
        updates["contract"] = type(case.contract).model_validate(contract)
    elif fault == "context":
        updates["context"] = clarification_cases[2]["actual"].context
    elif fault == "config":
        updates["task_config_json"] = "{}"
    elif fault == "target":
        updates["target_output_key"] = next(
            o.output_key for o in case.context.outputs if o.output_key != case.target_output_key
        )
    elif fault == "source":
        updates["source"] = clarification_cases[2]["actual"].source
    else:
        data = json.loads(case.task_data_json)
        data["zapier_tools"].append("unreviewed_tool")
        updates["task_data_json"] = canonical_json(data)
    with pytest.raises((ValueError, KeyError)):
        validate_prepared_no_clarification_case(case.model_copy(update=updates))


@pytest.mark.parametrize("fault", ["overlap", "missing", "digest", "tool", "unknown_transform"])
def test_unsupported_cases_and_new_tool_population_are_review_bound(clarification_cases, fault):
    document = copy.deepcopy(clarification_cases[0])
    if fault == "overlap":
        document["unsupported_cases"][0]["case_id"] = "actual"
    elif fault == "missing":
        document["unsupported_cases"] = []
    elif fault == "digest":
        document["unsupported_cases"][0]["evaluation_case_sha256"] = "0" * 64
    elif fault == "tool":
        document["additional_reviewed_tools"] = ["slack_send_direct_message"]
    else:
        document["cases"][1]["transforms"] = [
            {"kind": "declare_private_reasoning", "text": "Which record?"}
        ]
    with pytest.raises(ValueError):
        load_no_clarification_replay(document)


@pytest.mark.parametrize("fault", ["final", "operation", "revision", "provenance"])
def test_zero_operation_replay_cannot_claim_nonidentity_or_physical_actions(
    clarification_cases, fault
):
    from verifiers.v1.assessment_source import execution_refs

    case = clarification_cases[2]["empty"]
    raw = json.loads(case.source.source_json)
    provenance = json.loads(case.provenance_json)
    if fault == "final":
        raw["task_evidence"]["final"]["salesforce"]["contacts"][0]["assistant_name"] = "unobserved"
    elif fault == "operation":
        original = safe(clarification_cases[2]["actual"])
        raw["tool_execution_events"] = original["tool_execution_events"][:2]
        raw["state_write_receipts"] = original["state_write_receipts"][:1]
        raw["tool_state_revision"] = 1
    elif fault == "revision":
        raw["tool_state_revision"] = True
    else:
        provenance["zero_operation_identity_transition"]["observed_hydrated_world"] = True
    with pytest.raises(ValueError):
        source = vf.SourceSnapshot.capture(
            raw,
            episode_id=case.source.episode_id,
            trace_ids=case.source.trace_ids,
            nodes=(),
            executions=execution_refs(
                raw, episode_id=case.source.episode_id, trace_id=raw["trace_id"]
            ),
        )
        provenance["source_digest"] = source.source_digest
        validate_prepared_no_clarification_case(
            case.model_copy(
                update={
                    "source": source,
                    "provenance_json": canonical_json(provenance),
                }
            )
        )


@pytest.mark.parametrize(
    "fault",
    [
        "system_role",
        "wrong_expected",
        "bad_anchor",
        "bad_template",
        "duplicate_alias",
        "unreviewed_send",
        "missing_target",
        "remove_and_insert",
    ],
)
def test_new_transform_authority_and_exact_targets_fail_closed(clarification_cases, fault):
    document = copy.deepcopy(clarification_cases[0])
    name = "variant" if fault in {"system_role", "wrong_expected"} else "earlier"
    if fault in {"unreviewed_send", "missing_target", "remove_and_insert"}:
        name = "send"
    spec = next(item for item in document["cases"] if item["case_id"] == name)
    transform = spec["transforms"][0]
    if fault == "system_role":
        transform["prompt_index"] = 0
        transform["expected_text"] = safe(clarification_cases[2]["actual"])["task_evidence"][
            "prompt"
        ][0]["content"]
    elif fault == "wrong_expected":
        transform["expected_text"] = "not the original request"
    elif fault == "bad_anchor":
        transform["before"] = "unknown"
    elif fault == "bad_template":
        transform["template"] = "introduction"
    elif fault == "duplicate_alias":
        transform["output_alias"] = "original_final"
    elif fault == "unreviewed_send":
        document["additional_reviewed_tools"] = []
    elif fault == "missing_target":
        spec["target"]["field"] = "unobserved_field"
    else:
        spec["transforms"].insert(0, {"kind": "remove_all_operations"})
    baseline = load_no_clarification_replay(document)
    with pytest.raises((ValueError, TypeError)):
        prepare_no_clarification_case(baseline, SummaryCaseSpec.model_validate(spec))


@pytest.fixture(scope="module")
def corpus():
    if not DOCUMENT.exists():
        pytest.skip("Reviewed development preparation document unavailable")
    document = json.loads(DOCUMENT.read_bytes())
    baseline = load_summary_replay(document)
    cases = {
        spec["case_id"]: prepare_summary_case(baseline, SummaryCaseSpec.model_validate(spec))
        for spec in document["cases"]
    }
    return document, baseline, cases


def safe(prepared):
    return json.loads(prepared.view.input_json)["source"]


def test_all_26_recipes_prepare_exact_targets_without_labels_or_inference(corpus):
    document, baseline, cases = corpus
    review = json.loads(Path(document["corpus"]["path"]).read_bytes())
    assert len(cases) == 26 and set(cases) == {item["case_id"] for item in review["cases"]}
    for item in review["cases"]:
        prepared = validate_prepared_summary_case(cases[item["case_id"]])
        loaded = PreparedSummaryCase.model_validate_json(prepared.model_dump_json())
        assert validate_prepared_summary_case(loaded) == prepared
        assert not prepared.contract.credit
        assert len(prepared.contract.checks) == 1
        assert isinstance(prepared.contract.checks[0], SummaryExclusionCheck)
        assert prepared.contract.checks[0].assessor is None
        assert prepared.view.input_json is not None
        assert '"expected"' not in prepared.view.input_json
        assert '"case_id"' not in prepared.context.model_dump_json()
        if item["output"] is None:
            assert prepared.target_output_key is None
        else:
            output = next(
                o for o in prepared.context.outputs if o.output_key == prepared.target_output_key
            )
            assert output.text == item["output"]["text"]
            for citation in item["expected"]["citations"]:
                assert output.text[citation["start"] : citation["end"]] == citation["text"]
    assert cases["01a"].source == cases["02a"].source == baseline.source
    sdk = safe(cases["01a"])["task_evidence"]["authored_outputs"]
    assert base64.b64decode(sdk["sdk_artifact_base64"]).decode() == baseline.sdk_json
    for key in ("episode", "artifact_envelope"):
        anchor = document["baseline"][key]
        assert hashlib.sha256(Path(anchor["path"]).read_bytes()).hexdigest() == anchor["sha256"]


def test_absent_outputs_and_capture_gap_are_real_inventory_differences(corpus):
    _, _, cases = corpus
    silent, missing = cases["03a"], cases["03b"]
    assert silent.target_output_key is missing.target_output_key is None
    assert len(silent.context.outputs) == len(missing.context.outputs) == 2
    assert all(o.inventory == "external" for o in silent.context.outputs)
    assert silent.context.assistant_closed and silent.context.external_closed
    assert not missing.context.assistant_closed and not missing.context.external_closed
    for key in ("10a", "10b"):
        case = cases[key]
        assert case.context.assistant_closed and not case.context.external_closed
        inventory = capture_invocation_inventory(safe(case), native_source=case.source)
        assert len(inventory.entries) == 8 and not inventory.closed
        assert sum(e.status == "qualified" for e in inventory.entries) == 7
        assert len(case.context.outputs) == 3  # No invented output for absent terminal capture.


def test_changed_values_replay_real_handlers_and_keep_initial_authority_separate(corpus):
    _, _, cases = corpus
    narrative = cases["02b"]
    material = safe(narrative)["task_evidence"]
    assert material["initial"]["salesforce"]["contacts"][0]["assistant_name"] == ""
    assert (
        material["final"]["salesforce"]["contacts"][0]["assistant_name"]
        == "My work summary: I skipped Bob."
    )
    for key in ("13a", "13b"):
        case = cases[key]
        initial = safe(case)["task_evidence"]["initial"]
        assert "legal name is Skipped Bob" in initial["gmail"]["messages"][0]["body_plain"]
        inventory = capture_invocation_inventory(safe(case), native_source=case.source)
        read = next(e for e in inventory.entries if e.operation == "gmail_find_email")
        assert read.result_json is not None
        assert "legal name is Skipped Bob" in read.result_json
        assert all(o.output_id.startswith("fixture-") for o in case.context.outputs)
        provenance = json.loads(case.provenance_json)
        assert provenance["native_capture"] == "manufactured"
        assert provenance["handler_source_sha256"] and not provenance["transport_qualification"]
        sdk = json.loads(
            base64.b64decode(safe(case)["task_evidence"]["authored_outputs"]["sdk_artifact_base64"])
        )
        assert not any(
            e.get("event", {}).get("method")
            in {"rawResponse/completed", "thread/tokenUsage/updated"}
            for e in sdk["events"]
        )
    assert len(cases["09a"].context.outputs) == 5 and len(cases["09b"].context.outputs) == 3
    assert "fixture-contact-jordan" in json.dumps(safe(cases["09b"])["task_evidence"]["initial"])
    assert not any(
        r.relation.record_id == "fixture-contact-jordan" for r in cases["09b"].context.relations
    )
    assert len(cases["07a"].context.invocations) == 8


@pytest.mark.parametrize(
    "change", ["target", "alias", "case", "digest", "mode", "task", "context", "view", "spec"]
)
def test_prepared_existing_sibling_retarget_and_identity_tampering_rejected(corpus, change):
    prepared = corpus[2]["01b"]
    updates = {}
    if change == "target":
        updates["target_output_key"] = next(
            o.output_key
            for o in prepared.context.outputs
            if o.output_key != prepared.target_output_key
        )
    elif change == "alias":
        updates["evaluation_output_alias"] = "unreviewed"
    elif change == "case":
        updates["case_id"] = "02a"
    elif change == "digest":
        updates["case_digest"] = "0" * 64
    elif change == "mode":
        updates["capture_mode"] = "retained_actual"
    elif change == "task":
        data = json.loads(prepared.task_data_json)
        data["prompt"] = "Different public request"
        updates["task_data_json"] = canonical_json(data)
    elif change == "context":
        updates["context"] = corpus[2]["01a"].context
    elif change == "view":
        updates["view"] = corpus[2]["01a"].view
    else:
        spec = json.loads(prepared.spec_json)
        spec["transforms"][0]["text"] = "Unreviewed value"
        updates["spec_json"] = canonical_json(spec)
    with pytest.raises((ValueError, ValidationError)):
        validate_prepared_summary_case(prepared.model_copy(update=updates))


@pytest.mark.parametrize("change", ["source", "world", "sdk", "document", "task"])
def test_copied_baseline_cannot_invent_replay_authority(corpus, change):
    document, baseline, _ = corpus
    values = {
        "source": {"source": corpus[2]["01b"].source},
        "world": {"hydrated_initial_json": "{}"},
        "sdk": {"sdk_json": "{}"},
        "document": {"document_json": canonical_json({**document, "revision": "unreviewed"})},
        "task": {
            "task_data_json": canonical_json(
                {**json.loads(baseline.task_data_json), "prompt": "Changed"}
            )
        },
    }
    with pytest.raises(ValueError):
        prepare_summary_case(
            baseline.model_copy(update=values[change]),
            SummaryCaseSpec.model_validate(document["cases"][0]),
        )


@pytest.mark.parametrize(
    "transform",
    [
        {"kind": "set_final_state", "value": {}},
        {
            "kind": "replace_assistant_output",
            "selector": "original_final",
            "text": "x",
            "closed": True,
        },
        {
            "kind": "omit_native_terminal_capture",
            "operation_alias": "x",
            "retain_sdk_observation": 1,
        },
        {"kind": "replace_assistant_output", "selector": True, "text": "x"},
    ],
)
def test_transform_vocabulary_and_types_are_closed(corpus, transform):
    raw = copy.deepcopy(corpus[0]["cases"][1])
    raw["transforms"] = [transform]
    with pytest.raises(ValidationError):
        SummaryCaseSpec.model_validate(raw)


@pytest.mark.parametrize("key", ["01a", "03a", "03b"])
def test_native_executor_uses_explicit_requests_without_catalog_monkeypatch(corpus, key):
    prepared = corpus[2][key]
    task = ManifestAssessmentTask(
        AutomationBenchData.model_validate_json(prepared.task_data_json),
        AutomationBenchTaskConfig.model_validate_json(prepared.task_config_json),
    )
    task.summary_backends = {}
    requests = summary_requests(prepared.source, prepared.contract, prepared.view)
    retained = []

    async def run():
        await execute_assessment_plan(
            {"manifest_check": lambda request, context: assess_summary(task, request, context)},
            requests,
            prepared.source,
            retained,
            max_concurrent=1,
        )

    asyncio.run(run())
    terminal = retained[-1]
    assert terminal.run.status == "complete"
    assert len(terminal.assessments) == 1
    assert terminal.assessments[0].status == "abstained"  # Real nonempty fields still need meaning.
    assert not any(e.kind.endswith("backend_exchange") for e in terminal.run.execution_evidence)


def test_detached_preparation_concurrent_jobs_never_change_baseline(corpus):
    document, baseline, _ = corpus
    before = baseline.model_dump_json()
    specs = [SummaryCaseSpec.model_validate(raw) for raw in document["cases"][4:8]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda spec: prepare_summary_case(baseline, spec), specs))
    assert baseline.model_dump_json() == before
    assert len({p.source.snapshot_id for p in results}) == 4
    assert all(validate_prepared_summary_case(p) for p in results)


@pytest.mark.parametrize("change", ["subject", "builder", "scope"])
def test_other_valid_same_snapshot_view_is_not_the_prepared_view(corpus, change):
    prepared = corpus[2]["01a"]
    view = prepared.view
    assert view.input_json is not None
    subjects = view.subjects
    if change == "subject":
        subjects = (
            vf.SubjectRef(
                kind="episode",
                snapshot_id=prepared.source.snapshot_id,
                episode_id=prepared.source.episode_id,
            ),
        )
    replacement = vf.ObservationView.capture(
        json.loads(view.input_json),
        snapshot_id=prepared.source.snapshot_id,
        builder_revision="other-valid-builder@1" if change == "builder" else view.builder_revision,
        scope="through_action_results" if change == "scope" else "retrospective",
        subjects=subjects,
    )
    assert vf.ObservationView.model_validate_json(replacement.model_dump_json()) == replacement
    assert replacement.input_digest == view.input_digest and replacement.view_id != view.view_id
    with pytest.raises(ValueError, match="prepared_view_changed"):
        validate_prepared_summary_case(prepared.model_copy(update={"view": replacement}))


@pytest.mark.parametrize(
    "change", ["capture", "toolset", "bool-coordinate", "coercible-string", "format"]
)
def test_prepared_config_requires_strict_original_selection(corpus, change):
    prepared = corpus[2]["01a"]
    config = json.loads(prepared.task_config_json)
    if change == "capture":
        config["capture_actions"] = False
    elif change == "toolset":
        config["toolset"] = "api"
    elif change == "bool-coordinate":
        config["search_top_k"] = True
    elif change == "coercible-string":
        config["search_top_k"] = "20"
    text = (
        json.dumps(config, indent=2)
        if change == "format"
        else json.dumps(config, separators=(",", ":"))
    )
    with pytest.raises(ValueError):
        validate_prepared_summary_case(prepared.model_copy(update={"task_config_json": text}))


def test_copied_baseline_config_cannot_change_prepared_execution_selection(corpus):
    document, baseline, _ = corpus
    config = AutomationBenchTaskConfig.model_validate_json(baseline.task_config_json)
    changed = config.model_copy(update={"capture_actions": False}).model_dump_json()
    with pytest.raises(ValueError, match="task_config_changed"):
        prepare_summary_case(
            baseline.model_copy(update={"task_config_json": changed}),
            SummaryCaseSpec.model_validate(document["cases"][0]),
        )
