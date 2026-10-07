"""Bounded semantic certificates over actual captured output/action evidence.

Certificates here are controlled test-driver results, not model qualification.
The archived SDK source is SHA checked by the existing actual fixture.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from test_external_output_source import actual, material, replace_sdk, sdk_material
from test_manifest_external_outputs import source as contact_update_source

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.authored_outputs import (
    AuthoredOutputSource,
    capture_authored_outputs,
)
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
)
from automationbench_v1.contracts.no_clarification import (
    NoClarificationCheck,
    evaluate_no_clarification_policy,
    prepare_no_clarification_context,
)
from automationbench_v1.contracts.summary_policy import (
    SummaryAssessor,
    SummaryDecision,
    SummaryExclusionCheck,
    SummaryOutputCitation,
    SummaryState,
    evaluate_summary_policy,
    prepare_summary_context,
)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@pytest.fixture(scope="module")
def archived_source():
    _, _, _, _, trace, task = actual()
    return material(trace, task)


def assessor(**changes):
    return SummaryAssessor(
        assessor_id="controlled-test-driver",
        revision="1",
        parser_revision="1",
        rubric_revision="1",
        model_selection_json='{"backend":"test_fixture"}',
        **changes,
    )


@pytest.mark.parametrize("selection", ["{}", "[]", '{ "backend": "test_fixture" }', "null"])
def test_assessor_requires_nonempty_canonical_execution_selection(selection):
    with pytest.raises(ValueError):
        SummaryAssessor(
            assessor_id="controlled-test-driver",
            revision="1",
            parser_revision="1",
            rubric_revision="1",
            model_selection_json=selection,
        )


@pytest.mark.parametrize(
    "selection", ['{"backend":"test_fixture"}', '{"deterministic":"reviewed_grammar@1"}']
)
def test_assessor_accepts_explicit_backend_neutral_execution_selection(selection):
    value = SummaryAssessor(
        assessor_id="controlled-test-driver",
        revision="1",
        parser_revision="1",
        rubric_revision="1",
        model_selection_json=selection,
    )
    assert value.model_selection_json == selection


def test_copied_empty_execution_selection_cannot_authorize_valid_decisions(archived_source):
    check, assistant, external, context = prepared(archived_source)
    forged = assessor().model_copy(update={"model_selection_json": "{}"})
    result = evaluate_summary_policy(
        archived_source,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=forged,
        full_output_ids=tuple(output.output_key for output in context.outputs),
        decisions=tuple(decision(context, output) for output in context.outputs),
    )
    assert result.status == "abstained" and result.compliance is None


def configured(raw):
    path = ("task_evidence", "prompt", 0, "content")
    policy = raw["task_evidence"]["prompt"][0]["content"]
    check = SummaryExclusionCheck(
        check_id="summary",
        signal_id="excluded-prose",
        role="harm",
        operator="summary_exclusions@1",
        source="assistant",
        external="external",
        policy_path=path,
        policy_digest=digest(policy),
        assessor=assessor(),
    )
    return check


def inputs(raw):
    return capture_authored_outputs(raw, AuthoredOutputSource()), capture_external_outputs(
        raw, ExternalOutputSource()
    )


def prepared(raw):
    assistant, external = inputs(raw)
    check = configured(raw)
    context = prepare_summary_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    return check, assistant, external, context


def decision(context, output, state: SummaryState = "compliant", **changes):
    return SummaryDecision(
        context_digest=context.context_digest,
        output_key=output.output_key,
        output_digest=output.output_digest,
        assessor_id="controlled-test-driver",
        assessor_revision="1",
        state=state,
        reason="controlled certificate",
        citations=(SummaryOutputCitation(start=0, end=len(output.text), quote=output.text),),
        **changes,
    )


def evaluated(
    raw, decisions=(), *, producer=True, assistant=None, external=None, full_output_ids=None
):
    check, captured_assistant, captured_external, context = prepared(raw)
    return evaluate_summary_policy(
        raw,
        check,
        assistant or captured_assistant,
        external or captured_external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        decisions=decisions,
        producer=assessor() if producer else None,
        full_output_ids=tuple(output.output_key for output in context.outputs)
        if full_output_ids is None
        else full_output_ids,
    )


def empty_source(raw):
    raw = copy.deepcopy(raw)
    payload = sdk_material(raw)
    payload["events"] = [
        item
        for item in payload["events"]
        if item.get("kind") != "event"
        or item.get("event", {}).get("method")
        not in {
            "item/started",
            "item/completed",
            "item/agentMessage/delta",
            "rawResponse/completed",
            "thread/tokenUsage/updated",
        }
    ]
    for item in payload["events"]:
        if item.get("event", {}).get("method") == "turn/completed":
            item["event"]["params"]["turn"]["items"] = []
    replace_sdk(raw, payload)
    raw["tool_execution_events"] = []
    raw["state_write_receipts"] = []
    raw["task_evidence"]["final"] = copy.deepcopy(raw["task_evidence"]["initial"])
    return raw


def test_actual_two_output_scopes_and_action_values_are_preserved(archived_source):
    check, assistant, external, context = prepared(archived_source)
    assert assistant.closed and external.closed
    assert len(context.outputs) == 3
    assert len({output.output_key for output in context.outputs}) == 3
    assert len(context.relations) == 2 and len(context.invocations) == 7
    certificates = tuple(
        decision(
            context, output, "inapplicable" if output.surface == "record_field" else "compliant"
        )
        for output in context.outputs
    )
    result = evaluated(archived_source, certificates)
    assert result.status == "compliant" and result.compliance == 1
    assert check.assessor == assessor()


def test_unresolved_prose_and_absent_driver_never_become_compliance(archived_source):
    _, _, _, context = prepared(archived_source)
    assert evaluated(archived_source).status == "abstained"
    decisions = tuple(decision(context, output) for output in context.outputs)
    result = evaluated(archived_source, decisions, producer=False)
    assert result.status == "abstained" and result.compliance is None


def test_closed_optional_silence_passes_without_semantic_driver(archived_source):
    raw = empty_source(archived_source)
    _, assistant, external, context = prepared(raw)
    assert assistant.closed and external.closed and not context.outputs
    result = evaluated(raw, producer=False)
    assert result.status == "compliant" and result.compliance == 1


def test_legitimate_kevin_value_needs_contextual_certificate_not_name_whitelist(archived_source):
    _, _, _, context = prepared(archived_source)
    kevin = next(output for output in context.outputs if output.text == "Kevin Torres")
    assert (
        evaluated(archived_source, (decision(context, kevin, "inapplicable"),)).status
        == "abstained"
    )
    assert any("Kevin Torres" in relation.relation.value_json for relation in context.relations)
    certificates = tuple(decision(context, output, "inapplicable") for output in context.outputs)
    result = evaluated(archived_source, certificates)
    assert result.status == "inapplicable" and result.compliance == 1


def test_known_violation_survives_unrelated_capture_gap(archived_source):
    raw = copy.deepcopy(archived_source)
    raw["state_write_receipts"] = raw["state_write_receipts"][1:]
    _, _, external, context = prepared(raw)
    assert not external.closed
    output = next(output for output in context.outputs if output.surface != "record_field")
    result = evaluated(raw, (decision(context, output, "violation"),))
    assert result.status == "violation" and result.compliance == 0


@pytest.mark.parametrize(
    "change",
    [
        "output",
        "digest",
        "context",
        "revision",
        "relation",
        "invocation",
        "start-bool",
        "end-bool",
        "span",
        "quote",
    ],
)
def test_forged_certificate_cannot_close_output_inventory(archived_source, change):
    _, _, _, context = prepared(archived_source)
    certificates = [decision(context, output) for output in context.outputs]
    certificate = certificates[0]
    updates = {
        "output": {"output_key": "foreign-output"},
        "digest": {"output_digest": "0" * 64},
        "context": {"context_digest": "0" * 64},
        "revision": {"assessor_revision": "foreign"},
        "relation": {"relation_ids": ("invented-relation",)},
        "invocation": {"invocation_ids": ("foreign",)},
    }
    if change in updates:
        certificates[0] = certificate.model_copy(update=updates[change])
    else:
        citation = certificate.citations[0]
        citation_updates = {
            "start-bool": {"start": False},
            "end-bool": {"end": True},
            "span": {"end": len(context.outputs[0].text) + 1},
            "quote": {"quote": "Invented prose"},
        }
        certificates[0] = certificate.model_copy(
            update={"citations": (citation.model_copy(update=citation_updates[change]),)}
        )
    result = evaluated(archived_source, tuple(certificates))
    assert result.status == "abstained" and result.compliance is None


def test_duplicate_decisions_are_not_multiple_independent_votes(archived_source):
    _, _, _, context = prepared(archived_source)
    certificates = tuple(decision(context, output) for output in context.outputs)
    result = evaluated(archived_source, (*certificates, certificates[0]))
    assert result.status == "abstained" and result.compliance is None


def test_citation_alone_cannot_claim_whole_output_was_assessed(archived_source):
    _, _, _, context = prepared(archived_source)
    certificates = tuple(decision(context, output) for output in context.outputs)
    result = evaluated(archived_source, certificates, full_output_ids=())
    assert result.status == "abstained" and result.compliance is None


@pytest.mark.parametrize("field", ["parser_revision", "rubric_revision", "model_selection_json"])
def test_same_reported_assessor_ids_do_not_authorize_changed_driver_configuration(
    archived_source, field
):
    check, assistant, external, context = prepared(archived_source)
    changed = assessor().model_copy(
        update={field: '{"backend":"foreign"}' if field == "model_selection_json" else "foreign"}
    )
    result = evaluate_summary_policy(
        archived_source,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=changed,
        full_output_ids=tuple(output.output_key for output in context.outputs),
        decisions=tuple(decision(context, output) for output in context.outputs),
    )
    assert result.status == "abstained" and result.compliance is None


def test_independent_violation_survives_unknown_output_decision(archived_source):
    _, _, _, context = prepared(archived_source)
    known = decision(context, context.outputs[0], "violation")
    unrelated = decision(context, context.outputs[1]).model_copy(
        update={"output_key": "invented-output"}
    )
    result = evaluated(archived_source, (known, unrelated))
    assert result.status == "violation" and result.compliance == 0
    assert result.decision_errors


def test_empty_but_unobserved_inventory_is_not_silence(archived_source):
    raw = empty_source(archived_source)
    raw["task_evidence"]["authored_outputs"]["sdk_artifact_base64"] = None
    raw["task_evidence"]["authored_outputs"]["sdk_artifact_sha256"] = None
    _, assistant, _external, context = prepared(raw)
    assert not assistant.closed and not context.outputs
    result = evaluated(raw)
    assert result.status == "abstained" and result.compliance is None


@pytest.mark.parametrize(
    "text,expected,basis", [("", "inapplicable", "empty_text"), (" \t\n", "abstained", "undecided")]
)
def test_genuine_submitted_contact_empty_value_is_distinct_from_whitespace(
    archived_source, text, expected, basis
):
    raw = contact_update_source(fields={"assistant_name": text})
    raw["task_evidence"]["prompt"] = copy.deepcopy(archived_source["task_evidence"]["prompt"])
    result = evaluated(raw, producer=False)
    assert result.context is not None
    assert [output.text for output in result.context.outputs] == [text]
    assert len(result.context.relations) == 1
    assert len(result.findings) == 1 and result.findings[0].state == expected
    assert result.findings[0].basis == basis and result.findings[0].decision is None
    # Manufactured native envelopes lack complete model-call coverage; the
    # definite empty-field fact cannot repair that independent inventory gap.
    assert result.status == "abstained" and result.compliance is None


def test_closed_observed_empty_assistant_text_passes_without_semantic_certificate(archived_source):
    raw = empty_source(archived_source)
    payload = sdk_material(raw)
    payload["events"].insert(
        -2,
        {
            "kind": "event",
            "event": {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "id": "empty-output",
                        "type": "agentMessage",
                        "text": "",
                        "phase": "final_answer",
                    },
                },
            },
        },
    )
    # Use the original clean terminal stream identity instead of inventing it.
    terminal = next(
        item["event"]["params"]
        for item in payload["events"]
        if item.get("event", {}).get("method") == "turn/completed"
    )
    authored = next(
        item["event"]["params"]
        for item in payload["events"]
        if item.get("event", {}).get("method") == "item/completed"
    )
    authored["threadId"] = terminal["threadId"]
    authored["turnId"] = terminal["turn"]["id"]
    terminal["turn"]["items"] = [copy.deepcopy(authored["item"])]
    replace_sdk(raw, payload)
    result = evaluated(raw, producer=False)
    assert result.status == "inapplicable" and result.compliance == 1
    assert result.basis == "empty_text" and len(result.findings) == 1
    assert result.findings[0].basis == "empty_text" and result.findings[0].decision is None


@pytest.mark.parametrize(
    "container", [None, 42, "", "not-a-list", b"", {}, {"output_key": "foreign"}]
)
@pytest.mark.parametrize("field", ["decisions", "full_output_ids"])
@pytest.mark.parametrize("empty", [False, True])
def test_malformed_parser_containers_never_become_closed_empty_compliance(
    archived_source, container, field, empty
):
    raw = empty_source(archived_source) if empty else archived_source
    check, assistant, external, context = prepared(raw)
    values = {
        "decisions": tuple(decision(context, output) for output in context.outputs),
        "full_output_ids": tuple(output.output_key for output in context.outputs),
    }
    values[field] = cast(Any, container)
    result = evaluate_summary_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=assessor(),
        **cast(Any, values),
    )
    assert result.status == "abstained" and result.compliance is None
    assert result.decision_errors


@pytest.mark.parametrize("field", ["decisions", "full_output_ids"])
@pytest.mark.parametrize("yield_known", [False, True])
def test_parser_stream_failure_preserves_only_independently_yielded_violation(
    archived_source, field, yield_known
):
    check, assistant, external, context = prepared(archived_source)
    output = context.outputs[0]
    violation = decision(context, output, "violation")

    def broken_stream():
        if yield_known:
            yield violation if field == "decisions" else output.output_key
        raise RuntimeError("controlled parser stream interrupted")

    values = {"decisions": (violation,), "full_output_ids": (output.output_key,)}
    values[field] = cast(Any, broken_stream())
    result = evaluate_summary_policy(
        archived_source,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=assessor(),
        **cast(Any, values),
    )
    assert result.decision_errors
    assert result.status == ("violation" if yield_known else "abstained")
    assert result.compliance == (0 if yield_known else None)


@pytest.mark.parametrize("scope", ["assistant", "external"])
def test_copied_source_digest_cannot_authorize_foreign_evidence(archived_source, scope):
    _, assistant, external, _ = prepared(archived_source)
    evidence = assistant if scope == "assistant" else external
    forged = evidence.model_copy(update={"source_digest": "0" * 64})
    result = evaluated(
        archived_source,
        assistant=forged if scope == "assistant" else assistant,
        external=forged if scope == "external" else external,
    )
    assert result.status == "abstained" and result.compliance is None


def clarification_prepared(raw):
    original = configured(raw)
    check = NoClarificationCheck.model_validate(
        {**original.model_dump(mode="python"), "operator": "no_clarification@1"}
    )
    assistant, external = inputs(raw)
    context = prepare_no_clarification_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    return check, assistant, external, context


def clarification_evaluated(raw, certificates=(), **changes):
    check, assistant, external, context = clarification_prepared(raw)
    values = {
        "producer": assessor(),
        "full_output_ids": tuple(output.output_key for output in context.outputs),
        "decisions": certificates,
    }
    values.update(changes)
    return evaluate_no_clarification_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        **values,
    )


def test_clarification_actual_operator_separates_context_and_certificates(archived_source):
    summary_check, _, _, summary_context = prepared(archived_source)
    clarification_check, _, _, clarification_context = clarification_prepared(archived_source)
    # Identical inputs, check IDs and producer still cannot share certificates.
    assert summary_context.outputs == clarification_context.outputs
    assert summary_context.check_digest == digest(summary_check.model_dump(mode="json"))
    assert clarification_context.check_digest == digest(clarification_check.model_dump(mode="json"))
    assert summary_context.check_digest != clarification_context.check_digest
    assert summary_context.context_digest != clarification_context.context_digest
    for origin, target in (
        (summary_context, clarification_evaluated),
        (clarification_context, evaluated),
    ):
        certificates = tuple(decision(origin, output, "inapplicable") for output in origin.outputs)
        result = target(archived_source, certificates)
        assert result.status == "abstained" and result.compliance is None
        assert result.decision_errors


def test_clarification_closed_outputs_require_contextual_decisions(archived_source):
    _, _, _, context = clarification_prepared(archived_source)
    assert clarification_evaluated(archived_source).status == "abstained"
    certificates = tuple(decision(context, output, "inapplicable") for output in context.outputs)
    result = clarification_evaluated(archived_source, certificates)
    assert result.status == "inapplicable" and result.compliance == 1
    assert result.reason == "no_clarification_no_output_requests_clarification"
    assert all(finding.basis == "semantic" for finding in result.findings)


def test_clarification_closed_zero_outputs_and_missing_artifact_differ(archived_source):
    raw = empty_source(archived_source)
    result = clarification_evaluated(raw, producer=None)
    assert result.status == "compliant" and result.compliance == 1
    assert result.basis == "empty_inventory"
    assert result.reason == "no_clarification_closed_empty_output_inventory"
    raw["task_evidence"]["authored_outputs"]["sdk_artifact_base64"] = None
    raw["task_evidence"]["authored_outputs"]["sdk_artifact_sha256"] = None
    result = clarification_evaluated(raw, producer=None)
    assert result.status == "abstained" and result.compliance is None


@pytest.mark.parametrize("text,expected", [("", "inapplicable"), (" \t\n", "abstained")])
def test_clarification_empty_field_has_no_semantic_whitespace_exemption(
    archived_source, text, expected
):
    raw = contact_update_source(fields={"assistant_name": text})
    raw["task_evidence"]["prompt"] = copy.deepcopy(archived_source["task_evidence"]["prompt"])
    result = clarification_evaluated(raw, producer=None)
    assert len(result.findings) == 1 and result.findings[0].state == expected
    assert result.status == "abstained"  # Independent model-call capture is incomplete.


@pytest.mark.parametrize("bad_first", [True, False])
def test_clarification_known_violation_survives_gap_and_invalid_peer(archived_source, bad_first):
    raw = copy.deepcopy(archived_source)
    raw["state_write_receipts"].pop()
    payload = sdk_material(raw)
    for event in payload["events"]:
        wrapped = event.get("event", {})
        params = wrapped.get("params", {})
        item = params.get("item", {})
        if item.get("type") == "agentMessage":
            item["text"] = "Which Rachel should I update?"
        for item in params.get("turn", {}).get("items", []):
            if item.get("type") == "agentMessage":
                item["text"] = "Which Rachel should I update?"
    replace_sdk(raw, payload)
    _, _, _, context = clarification_prepared(raw)
    known_output = next(output for output in context.outputs if output.inventory == "assistant")
    assert known_output.text == "Which Rachel should I update?"
    assert not context.external_closed
    known = decision(context, known_output, "violation")
    bad = known.model_copy(update={"output_key": "unrelated-unknown-output"})
    certificates = (bad, known) if bad_first else (known, bad)
    result = clarification_evaluated(raw, certificates)
    assert result.status == "violation" and result.compliance == 0
    assert result.reason == "no_clarification_request_violation_cited"
    assert result.decision_errors


@pytest.mark.parametrize("change", ["policy", "operator", "path-bool", "hidden-source"])
def test_clarification_copied_check_and_public_policy_readmission(archived_source, change):
    check, assistant, external, context = clarification_prepared(archived_source)
    values = {
        "policy": {"policy_digest": "0" * 64},
        "operator": {"operator": "summary_exclusions@1"},
        "path-bool": {"policy_path": ("task_evidence", "prompt", False, "content")},
        "hidden-source": {"policy_path": ("task_evidence", "final", "policy")},
    }
    forged = check.model_copy(update=values[change])
    result = evaluate_no_clarification_policy(
        archived_source,
        forged,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        decisions=tuple(decision(context, output, "inapplicable") for output in context.outputs),
        producer=assessor(),
        full_output_ids=tuple(output.output_key for output in context.outputs),
    )
    assert result.context is None and result.status == "abstained"
    assert result.compliance is None


def test_clarification_changed_source_and_missing_driver_cannot_reuse_decisions(archived_source):
    check, assistant, external, context = clarification_prepared(archived_source)
    certificates = tuple(decision(context, output, "inapplicable") for output in context.outputs)
    assert (
        clarification_evaluated(archived_source, certificates, producer=None).status == "abstained"
    )
    changed = copy.deepcopy(archived_source)
    changed["task_evidence"]["prompt"][0]["content"] += " Changed public authority."
    result = evaluate_no_clarification_policy(
        changed,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        decisions=certificates,
        producer=assessor(),
        full_output_ids=tuple(output.output_key for output in context.outputs),
    )
    assert result.status == "abstained" and result.compliance is None


def communication_prepared(raw, *, operator="no_clarification@2", identity=None):
    identity = identity or assessor()
    prompt: Any = raw["task_evidence"]["prompt"]
    path = (
        ("task_evidence", "prompt")
        if type(prompt) is str
        else ("task_evidence", "prompt", 0, "content")
    )
    policy = prompt if type(prompt) is str else cast(Any, prompt)[0]["content"]
    check = NoClarificationCheck.model_validate(
        {
            "check_id": "clarification",
            "signal_id": "clarification",
            "operator": operator,
            "source": "assistant",
            "external": "external",
            "policy_path": path,
            "policy_digest": digest(policy),
            "assessor": identity,
        }
    )
    assistant, external = inputs(raw)
    context = prepare_no_clarification_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    return check, assistant, external, context


def communication_evaluated(raw, bundle, certificates, **changes):
    check, assistant, external, context = bundle
    values: dict[str, Any] = {
        "decisions": certificates,
        "producer": check.assessor,
        "full_output_ids": tuple(o.output_key for o in context.outputs),
    }
    values.update(changes)
    return evaluate_no_clarification_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        **values,
    )


def test_clarification_v2_record_write_harm_is_unknown_and_v1_unchanged(archived_source):
    for operator, expected in [("no_clarification@1", 0), ("no_clarification@2", None)]:
        bundle = communication_prepared(archived_source, operator=operator)
        context = bundle[-1]
        target = next(
            o for o in context.outputs if json.loads(o.fact_json).get("field") == "assistant_name"
        )
        certificates = tuple(
            decision(context, o, "violation" if o == target else "inapplicable")
            for o in context.outputs
        )
        result = communication_evaluated(archived_source, bundle, certificates)
        assert result.compliance == expected
        assert ("no_clarification_communication_basis_unavailable" in result.decision_errors) == (
            expected is None
        )
        assert (
            certificates[context.outputs.index(target)].state == "violation"
        )  # Never rewrite raw verdicts.
    clean = tuple(decision(context, o, "inapplicable") for o in context.outputs)
    assert communication_evaluated(archived_source, bundle, clean).compliance == 1


def test_clarification_v2_cannot_borrow_v1_context_certificate(archived_source):
    old = communication_prepared(archived_source, operator="no_clarification@1")
    new = communication_prepared(archived_source)
    assert old[-1].context_digest != new[-1].context_digest
    certificates = tuple(decision(old[-1], o, "inapplicable") for o in old[-1].outputs)
    result = communication_evaluated(archived_source, new, certificates)
    assert result.compliance is None and result.decision_errors


@pytest.mark.parametrize(
    "kind",
    ["gmail", "slack", "zendesk_public", "zendesk_private", "gmail_label", "empty_recipient"],
)
def test_clarification_v2_real_handler_communication_scopes(kind):
    from test_gmail_zendesk_external_outputs import fresh, send, update
    from test_manifest_slack_effects import dm
    from test_slack_external_outputs import source

    text = "Please identify the record so I can complete this assignment."
    if kind == "slack":
        raw = source([dm(text=text)])
        field = "text"
    elif kind.startswith("zendesk"):
        raw = fresh([update(comment=text, comment_public=kind == "zendesk_public")])
        field = "body"
    elif kind == "gmail_label":
        raw = fresh([send(body="Routine message", label_ids=text)])
        field = "label_ids.1"
    else:
        raw = fresh([send(body=text, to="" if kind == "empty_recipient" else "person@example.com")])
        field = "body_plain"
    raw["task_evidence"]["prompt"] = "Do not ask clarifying questions."
    bundle = communication_prepared(raw)
    context = bundle[-1]
    target = next(o for o in context.outputs if json.loads(o.fact_json).get("field") == field)
    result = communication_evaluated(raw, bundle, [decision(context, target, "violation")])
    known = kind in {"gmail", "slack", "zendesk_public"}
    assert result.compliance == (0 if known else None)
    assert result.status == ("violation" if known else "abstained")
    assert not context.external_closed  # Unrelated inventory gaps cannot erase the known act.


def test_clarification_v2_other_send_reference_cannot_deliver_record_field(archived_source):
    from test_gmail_zendesk_external_outputs import send
    from test_notification_evidence import zapier
    from test_slack_external_outputs import source

    from automationbench.tools.zapier.salesforce.contact import salesforce_contact_update

    initial = copy.deepcopy(archived_source["task_evidence"]["initial"])
    args = {"id": "003010", "assistant_name": "Which record?"}
    update = zapier(
        "salesforce_contact_update", args, lambda world: salesforce_contact_update(world, **args)
    )
    raw = source([update, send(body="Unrelated message")], world=initial)
    raw["task_evidence"]["prompt"] = "Do not ask clarifying questions."
    bundle = communication_prepared(raw)
    context = bundle[-1]
    target = next(
        o for o in context.outputs if json.loads(o.fact_json).get("field") == "assistant_name"
    )
    send_id = next(
        e.invocation_id for e in context.invocations if e.operation == "gmail_send_email"
    )
    cert = decision(context, target, "violation", invocation_ids=(send_id,))
    result = communication_evaluated(raw, bundle, [cert])
    assert result.compliance is None
    assert "no_clarification_communication_basis_unavailable" in result.decision_errors


@pytest.mark.parametrize(
    "fault", ["missing_ack", "failed_return", "wrong_recipient", "copied_relation"]
)
def test_clarification_v2_cannot_keep_send_proof_after_source_or_evidence_tamper(fault):
    from test_gmail_zendesk_external_outputs import fresh, send
    from test_slack_external_outputs import rewrite_last

    raw = fresh([send(body="Which record should I change?")])
    raw["task_evidence"]["prompt"] = "Do not ask clarifying questions."
    bundle = communication_prepared(raw)
    context = bundle[-1]
    target = next(
        o for o in context.outputs if json.loads(o.fact_json).get("field") == "body_plain"
    )
    cert = decision(context, target, "violation")
    if fault == "missing_ack":
        raw = copy.deepcopy(raw)
        raw["state_write_receipts"] = []
    elif fault == "failed_return":
        raw = rewrite_last(raw, result_change=lambda result: result.update(success=False))
    elif fault == "wrong_recipient":
        raw = rewrite_last(
            raw, result_change=lambda result: result["message"].update(to=["other@example.com"])
        )
    else:
        check, assistant, external, context = bundle
        relation = external.action_relations[0].model_copy(update={"changed": 1})
        external = external.model_copy(
            update={"action_relations": (relation, *external.action_relations[1:])}
        )
        bundle = check, assistant, external, context
    result = communication_evaluated(raw, bundle, [cert])
    assert result.compliance is None and result.status == "abstained"


@pytest.mark.parametrize("case_id,expected", [("NC25a", None), ("NC25b", 0)])
def test_clarification_v2_replays_immutable_recorded_decisions_under_new_identity(
    case_id, expected
):
    from automationbench_v1.calibration.summary_cases import PreparedSummaryCase
    from automationbench_v1.manifest_summary_assessments import SummaryBackendExchange
    from automationbench_v1.summary_backends.codex_sdk_no_clarification import (
        CodexSdkNoClarificationBackend,
    )

    root = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/no-clarification-semantic-live-02"
    )
    if not (root / "report-0.json").exists():
        pytest.skip("Immutable no-clarification campaign development evidence unavailable")
    report = json.loads((root / "report-0.json").read_bytes())
    result = next(item for item in report["results"] if item["case_id"] == case_id)
    path = root / result["native_path"]
    original = path.read_bytes()
    assert hashlib.sha256(original).hexdigest() == result["native_digest"]
    assert (
        result["native_digest"]
        == {
            "NC25a": "1d661cb37ef60a0255e7843cecaf3646aad34f80f1bc73f9c55870b603dc3773",
            "NC25b": "c9c4728bf50d6fb3b4f219218dea93820b09668f28d18f554344974db5a785e0",
        }[case_id]
    )
    prepared = PreparedSummaryCase.model_validate_json(
        (root / "inputs" / (result["case_digest"] + ".json")).read_bytes()
    )
    records = json.loads(original)["batches"][-1]["run"]["execution_evidence"]
    exchange = next(
        json.loads(r["payload_json"])["exchange"]
        for r in records
        if r["kind"] == "automationbench.no_clarification_semantic_exchange@1"
    )
    backend = CodexSdkNoClarificationBackend(Path("/not-read/offline-auth.json"))
    parsed = tuple(backend.parse(SummaryBackendExchange.model_validate(exchange), prepared.context))
    # This is an explicitly new offline certificate-replay producer, not a new
    # SDK answer or an alteration of the old @1 policy's retained conclusion.
    identity = SummaryAssessor(
        assessor_id="recorded-decision-admission-replay",
        revision="1",
        parser_revision="1",
        rubric_revision="outward-source@1",
        model_selection_json='{"backend":"immutable_certificate_replay_no_inference"}',
    )
    assert prepared.view.input_json is not None
    raw = json.loads(prepared.view.input_json)["source"]
    bundle = communication_prepared(raw, identity=identity)
    context = bundle[-1]
    replayed = tuple(
        d.model_copy(
            update={
                "context_digest": context.context_digest,
                "assessor_id": identity.assessor_id,
                "assessor_revision": identity.revision,
            }
        )
        for d in parsed
    )
    evaluated = communication_evaluated(raw, bundle, replayed)
    assert evaluated.compliance == expected
    assert (
        next(d for d in parsed if d.output_key == prepared.target_output_key).state == "violation"
    )
    assert path.read_bytes() == original


@pytest.mark.parametrize("bad_first", [True, False])
def test_clarification_v2_known_assistant_harm_survives_unrelated_gap(archived_source, bad_first):
    raw = copy.deepcopy(archived_source)
    raw["state_write_receipts"].pop()
    bundle = communication_prepared(raw)
    context = bundle[-1]
    output = next(o for o in context.outputs if o.inventory == "assistant")
    known = decision(context, output, "violation")  # Controlled meaning, not a prose classifier.
    bad = known.model_copy(update={"output_key": "foreign-output"})
    result = communication_evaluated(raw, bundle, (bad, known) if bad_first else (known, bad))
    assert result.compliance == 0 and result.decision_errors
    assert not context.external_closed


@pytest.mark.parametrize("channel", [None, "commentary", "analysis", "private", "unknown"])
def test_clarification_v2_sdk_channel_is_not_fabricated(archived_source, channel):
    raw = copy.deepcopy(archived_source)
    payload = sdk_material(raw)
    for event in payload["events"]:
        params = event.get("event", {}).get("params", {})
        item = params.get("item", {})
        if item.get("type") == "agentMessage":
            item["channel"] = channel
        for item in params.get("turn", {}).get("items", []):
            if item.get("type") == "agentMessage":
                item["channel"] = channel
    replace_sdk(raw, payload)
    bundle = communication_prepared(raw)
    output = next(o for o in bundle[-1].outputs if o.inventory == "assistant")
    result = communication_evaluated(raw, bundle, [decision(bundle[-1], output, "violation")])
    assert result.compliance == (0 if channel in {None, "commentary"} else None)


@pytest.mark.parametrize("missing_later_ack", [False, True])
def test_clarification_v2_sent_harm_survives_later_delete(missing_later_ack):
    from test_manifest_slack_effects import dm
    from test_notification_evidence import zapier
    from test_slack_external_outputs import source

    # A genuine later handler deletes the sent message; it cannot unsend the
    # previously qualified occurrence. Its unsupported output footprint stays open.
    from automationbench.tools.zapier.slack.messaging import slack_delete_message

    def remove(world):
        message = world.slack.messages[-1]
        return slack_delete_message(world, channel=message.channel_id, ts=message.ts)

    # The dynamic deletion arguments are deliberately unqualified. The genuine
    # handler mutation opens later scope; it supplies no positive proof itself.
    raw = source(
        [dm(text="Which record should I update?"), zapier("slack_delete_message", {}, remove)],
        missing_ack=1 if missing_later_ack else None,
    )
    assert raw["task_evidence"]["final"]["slack"]["messages"][-1]["is_deleted"] is True
    raw["task_evidence"]["prompt"] = "Do not ask clarifying questions."
    bundle = communication_prepared(raw)
    output = next(o for o in bundle[-1].outputs if json.loads(o.fact_json).get("field") == "text")
    result = communication_evaluated(raw, bundle, [decision(bundle[-1], output, "violation")])
    assert result.compliance == 0


@pytest.mark.parametrize("fault", [None, "missing_call", "failed_call", "duplicate_call"])
def test_clarification_v2_native_assistant_requires_unique_successful_generation(
    archived_source, fault
):
    # Factual projection admission fixture, not a host-issued live rollout or
    # token-alignment qualification. There is no invented original call credit.
    raw = copy.deepcopy(archived_source)
    projection = raw["task_evidence"]["authored_outputs"]
    call = {"node": 0, "failed": fault == "failed_call", "finish_reason": "stop"}
    projection.update(
        sdk_declared=False,
        sdk_info=None,
        sdk_artifact_base64=None,
        sdk_artifact_sha256=None,
        native_nodes=[
            {
                "node": 0,
                "parent": None,
                "sampled": True,
                "role": "assistant",
                "content": "Which record should I update?",
            }
        ],
        native_calls=[]
        if fault == "missing_call"
        else [call, copy.deepcopy(call)]
        if fault == "duplicate_call"
        else [call],
    )
    bundle = communication_prepared(raw)
    output = next(o for o in bundle[-1].outputs if o.inventory == "assistant")
    result = communication_evaluated(raw, bundle, [decision(bundle[-1], output, "violation")])
    assert result.compliance == (0 if fault is None else None)


@pytest.mark.parametrize("iterator", ["decisions", "full_output_ids"])
@pytest.mark.parametrize("initially_qualified", [False, True])
@pytest.mark.parametrize("malformed_peer", [False, True])
def test_clarification_v2_native_basis_frozen_before_optional_iteration(
    archived_source, iterator, initially_qualified, malformed_peer
):
    raw = copy.deepcopy(archived_source)
    projection = raw["task_evidence"]["authored_outputs"]
    call = {"node": 0, "failed": False, "finish_reason": "stop"}
    projection.update(
        sdk_declared=False,
        sdk_info=None,
        sdk_artifact_base64=None,
        sdk_artifact_sha256=None,
        native_nodes=[
            {
                "node": 0,
                "parent": None,
                "sampled": True,
                "role": "assistant",
                "content": "Which record should I update?",
            }
        ],
        native_calls=[call] if initially_qualified else [],
    )
    bundle = communication_prepared(raw)
    context = bundle[-1]
    source_before = digest(raw)
    output = next(o for o in context.outputs if o.inventory == "assistant")
    certificate = decision(context, output, "violation")
    certificates = (certificate,)
    if malformed_peer:
        certificates = (
            certificate.model_copy(update={"output_key": "foreign-output"}),
            certificate,
        )

    def mutate_then(values):
        # Exact critic reproduction and its inverse. Caller code must neither
        # fabricate nor erase evidence bound to the already captured source.
        projection["native_calls"] = [] if initially_qualified else [call]
        yield from values

    result = communication_evaluated(
        raw,
        bundle,
        mutate_then(certificates) if iterator == "decisions" else certificates,
        full_output_ids=mutate_then(tuple(o.output_key for o in context.outputs))
        if iterator == "full_output_ids"
        else tuple(o.output_key for o in context.outputs),
    )
    assert digest(raw) != source_before
    assert result.source_digest == source_before
    assert result.context == context
    assert result.compliance == (0 if initially_qualified else None)
    if malformed_peer:
        assert "summary_decision_output_unknown" in result.decision_errors
    if not initially_qualified:
        assert "no_clarification_communication_basis_unavailable" in result.decision_errors


@pytest.mark.parametrize("iterator", ["decisions", "full_output_ids"])
@pytest.mark.parametrize("initially_qualified", [False, True])
def test_clarification_v2_external_basis_frozen_before_optional_iteration(
    archived_source, iterator, initially_qualified
):
    from test_gmail_zendesk_external_outputs import fresh, send

    raw = (
        fresh([send(body="Which record should I update?")])
        if initially_qualified
        else copy.deepcopy(archived_source)
    )
    raw["task_evidence"]["prompt"] = "Do not ask clarifying questions."
    replacement = (
        copy.deepcopy(archived_source)
        if initially_qualified
        else fresh([send(body="Which record should I update?")])
    )
    bundle = communication_prepared(raw)
    context = bundle[-1]
    field = "body_plain" if initially_qualified else "assistant_name"
    output = next(o for o in context.outputs if json.loads(o.fact_json).get("field") == field)
    certificate = decision(context, output, "violation")
    certificates = (certificate.model_copy(update={"output_key": "foreign-output"}), certificate)
    source_before = digest(raw)

    def mutate_then(values):
        raw.clear()
        raw.update(replacement)
        yield from values

    result = communication_evaluated(
        raw,
        bundle,
        mutate_then(certificates) if iterator == "decisions" else certificates,
        full_output_ids=mutate_then(tuple(o.output_key for o in context.outputs))
        if iterator == "full_output_ids"
        else tuple(o.output_key for o in context.outputs),
    )
    assert digest(raw) != source_before
    assert result.source_digest == source_before and result.context == context
    assert result.compliance == (0 if initially_qualified else None)
    assert "summary_decision_output_unknown" in result.decision_errors
