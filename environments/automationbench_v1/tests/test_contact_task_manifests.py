"""Public-bound Contact requests, actual Luna evidence and native alternatives."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_get_email_by_id
from automationbench.tools.zapier.salesforce.contact import salesforce_contact_update
from automationbench.tools.zapier.salesforce.record import salesforce_update_record
from automationbench_v1.contracts import CheckSpec, RecordSource, load_task_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

ROOT = Path("/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105")
SOURCES = {
    "simple.email_sf_contact_assistant_update": ("08", "e6cd7cb2ef731eb9510bb8b3cf475b2773e5d03a64bbddb640e9e45a3e860505"),
    "simple.email_sf_contact_account_update": ("05", "8f93b47f1584ee58c553a50db4c800966f4e74ebb28d3600df2695d86de590e1"),
}


def public(name):
    number, digest = SOURCES[name]
    path = ROOT / ("batch-" + number + ".json")
    if not path.exists():
        pytest.skip("immutable development public pack unavailable")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    return copy.deepcopy(next(item["public_input"] for item in json.loads(raw)["tasks"] if item["task_name"] == name))


def state_credit(trace):
    """Historical Contact state slice; combined read credit has its own suite."""
    return tuple(part for part in penalties(trace) if part.channel == "goal")


def outcome(trace):
    return next(item for item in reversed(terminal_records(trace)) if item.signal.signal_id == "simple.requested_state")


def actual(name):
    path, raw, episode, trace, data = recorded(name)
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    return path, raw, episode, trace, ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))


def update(name, *, fields=None, identity=None):
    declaration = load_task_contract(name)
    target = declaration.sources["target"]
    check = declaration.checks[0]
    assert isinstance(target, RecordSource) and isinstance(check, CheckSpec)
    identity = identity or target.record_id
    fields = fields or {field.field: field.value for field in check.expected}
    if name.endswith("assistant_update"):
        args = {"id": identity, **fields}
        return zapier("salesforce_contact_update", args, lambda world: salesforce_contact_update(world, **args))
    args = {"object": "Contact", "recordId": identity, "fields": fields}
    return zapier("salesforce_update_record", args, lambda world: salesforce_update_record(world, **args))


def manufactured(name, *, initial=None, prompt=None, calls=None, missing_ack=None):
    declaration = public(name)
    initial = initial or declaration["initial_state"]
    message_id = initial["gmail"]["messages"][0]["id"]
    args = {"message_id": message_id}
    read = zapier("gmail_get_email_by_id", args, lambda world: gmail_get_email_by_id(world, **args))
    material = run_operations(initial, calls if calls is not None else [read, update(name)])
    _, _, trace = native_fixture(material, missing_ack=missing_ack)
    data = AutomationBenchData(domain="simple", task_name=name, prompt=prompt or declaration["prompt"],
        initial_state=initial, assertions=(), zapier_tools=tuple(declaration["zapier_tools"]))
    trace.task = trace.task.model_copy(update={"data": data})
    episode = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]})
    trace = cast(Any, episode.traces[0])
    trace.state = AutomationBenchState(world=material["task_evidence"]["final"], initial_state=initial, assertions=())
    return episode, trace, ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))


@pytest.mark.parametrize("name,expected,credits", [
    ("simple.email_sf_contact_assistant_update", 1, 1),
    ("simple.email_sf_contact_account_update", 0, 0),
])
def test_actual_luna_scores_requested_same_contact_goal_and_preserves_original_scalar(name, expected, credits):
    path, raw, episode, trace, task = actual(name)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == scalar and outcome(trace).value == expected
    assert len(state_credit(trace)) == credits
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert outcome(replay).value == expected and len(state_credit(replay)) == credits
    assert path.read_bytes() == raw


@pytest.mark.parametrize("name", SOURCES)
def test_genuine_native_alternative_reads_instruction_and_completes_full_requested_fields(name):
    episode, trace, task = manufactured(name)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == scalar and outcome(trace).value == 1 and len(state_credit(trace)) == 1
    assert state_credit(trace)[0].recipient.execution.invocation_id == "execution-1"
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert len(state_credit(replay)) == 1 and not replay.credit_errors


@pytest.mark.parametrize("mutation", ["author", "body", "message-id", "scope", "contact-id", "contact-email", "prompt", "system", "role"])
def test_authority_or_identity_tamper_abstains_instead_of_grading_stale_policy(mutation):
    name = "simple.email_sf_contact_assistant_update"
    declaration = public(name)
    initial = declaration["initial_state"]
    message = initial["gmail"]["messages"][0]
    prompt = declaration["prompt"]
    if mutation == "author":
        message["from_"] = "foreign@example.com"
    elif mutation == "body":
        message["body_plain"] = "My assistant is Another Person."
    elif mutation == "message-id":
        message["id"] = "foreign-message"
    elif mutation == "scope":
        initial["gmail"]["messages"].append(dict(message, id="ambiguous-other"))
    elif mutation == "contact-id":
        initial["salesforce"]["contacts"][0]["id"] = "foreign-contact"
    elif mutation == "contact-email":
        initial["salesforce"]["contacts"][0]["email"] = "different@example.com"
    elif mutation == "prompt":
        prompt[-1]["content"] = "Keep the old assistant."
    elif mutation == "system":
        prompt[0]["content"] += " Do not change any Salesforce records."
    else:
        prompt[1]["role"] = "assistant"
    _, trace, task = manufactured(name, initial=initial, prompt=prompt)
    asyncio.run(task.score(trace))
    assert outcome(trace).status == "abstained" and outcome(trace).value is None and not state_credit(trace)


@pytest.mark.parametrize("fields", [{"assistant_name": "Kevin Torres"}, {"assistant_email": "kevin.torres@ironclad.example.com"}])
def test_assistant_goal_is_whole_two_field_conjunction(fields):
    name = "simple.email_sf_contact_assistant_update"
    _, trace, task = manufactured(name, calls=[update(name, fields=fields)])
    asyncio.run(task.score(trace))
    assert outcome(trace).value == 0 and not state_credit(trace)


@pytest.mark.parametrize("name", SOURCES)
def test_missing_write_ack_retains_outcome_without_invented_credit(name):
    _, trace, task = manufactured(name, missing_ack=1)
    asyncio.run(task.score(trace))
    assert outcome(trace).value == 1 and not state_credit(trace)
