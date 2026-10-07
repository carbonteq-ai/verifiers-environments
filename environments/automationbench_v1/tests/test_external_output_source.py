"""SHA-bound SDK/native coverage reconciliation, not call attribution or policy.

Mutations are coherent in-memory counterexamples; retained source files are never
rewritten. Record-field strings remain candidate text even in structured slots.
"""

import base64
import copy
import hashlib
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_authored_output_source import ENVELOPE_SHA, EPISODE_SHA, NAME, SDK_SHA
from test_batch01_manifests import recorded
from verifiers.v1.assessment_source import capture_trace_source

from automationbench_v1.calibration.collector import read_retained_artifacts
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
    validate_external_outputs,
)
from automationbench_v1.contracts.invocation_inventory import (
    capture_invocation_inventory,
    validate_invocation_inventory,
)
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

PAIRS = {
    'call_cZkX5YCsgKoCYhbfwDy2xE6Z': '180b9687ade249f18f88d5e42b65cb53',
    'call_Sw38GTTRWzWFrFVOdXYKtHP4': 'd69ac9aee33d4d8cb6e8cc781eb0c9e0',
    'call_pmY5emdyNsT0s81f4o2IIJww': '2d9abd8b59804bd6b2a0ef024285f60c',
    'call_NkXDe88BBptA8aVrAPBXPSdx': 'eb45e8e2c5c648c1bce3fdb9994f3c29',
    'call_D9kx4KQApuWfRn0JSrolgktR': 'd66e70a074194d77bf6d92562359a987',
    'call_LLC4TZkZyEiXagtJyDDEIID2': 'e5eedd167fe74f1e9994fbc722a811f0',
    'call_FU20xbnrzMEgTh2oDVUlqAU0': '8baf7cd9ff6549b49fd1f565a59ad93a',
}


def actual():
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    envelope = (path.parent / 'trace-0-artifacts.json').read_bytes()
    assert hashlib.sha256(envelope).hexdigest() == ENVELOPE_SHA
    artifacts = read_retained_artifacts(path.parent, trace)
    assert hashlib.sha256(cast(bytes, artifacts['codex_sdk/events.json'])).hexdigest() == SDK_SHA
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=artifacts)
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    return path, raw, envelope, episode, trace, task


def material(trace, task):
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    return json.loads(source.source_json)


@pytest.fixture(scope='module')
def original_source():
    _, _, _, _, trace, task = actual()
    return material(trace, task)


def sdk_material(source):
    return json.loads(base64.b64decode(source['task_evidence']['authored_outputs']['sdk_artifact_base64']))


def replace_sdk(source, payload):
    encoded = canonical_json(payload).encode()
    raw = source['task_evidence']['authored_outputs']
    raw['sdk_info'] = copy.deepcopy(payload)
    raw['sdk_artifact_base64'] = base64.b64encode(encoded).decode()
    raw['sdk_artifact_sha256'] = hashlib.sha256(encoded).hexdigest()


def completed_calls(payload):
    return [record['event']['params']['item'] for record in payload['events']
        if record.get('kind') == 'event' and record.get('event', {}).get('method') == 'item/completed'
        and record['event'].get('params', {}).get('item', {}).get('type') == 'mcpToolCall']


def test_actual_seven_call_bijection_expands_only_installed_discovery_default(original_source):
    source = copy.deepcopy(original_source)
    before = canonical_json(source)
    inventory = capture_invocation_inventory(source)
    assert inventory.closed and len(inventory.entries) == 7
    assert all(entry.status == 'qualified' for entry in inventory.entries)
    assert {pair.sdk_item_id: pair.native_invocation_id for pair in inventory.sdk_coverage_pairs} == PAIRS
    sdk = sdk_material(source)
    assert sdk['mcp_item_execution_join'] == 'unqualified'
    calls = {item['id']: item for item in completed_calls(sdk)}
    for entry in inventory.entries:
        sdk_id = next(key for key, value in PAIRS.items() if value == entry.invocation_id)
        args = calls[sdk_id]['arguments']
        kwargs = json.loads(cast(str, entry.outer_arguments_json))
        if entry.outer_tool == 'search_tools':
            assert 'top_k' not in args and kwargs == {**args, 'top_k': 5}
        else:
            assert kwargs == args
    validate_invocation_inventory(inventory, source)
    assert canonical_json(source) == before


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'ambiguous', 'error', 'foreign-server',
    'argument', 'result', 'unknown-tool', 'pending'])
def test_sdk_inventory_disagreement_never_proves_external_scope_closed(original_source, mutation):
    source = copy.deepcopy(original_source)
    sdk = sdk_material(source)
    calls = completed_calls(sdk)
    first = calls[0]
    identity = first['id']
    if mutation == 'missing':
        sdk['events'] = [event for event in sdk['events']
            if event.get('event', {}).get('params', {}).get('item', {}).get('id') != identity]
    elif mutation in {'extra', 'ambiguous'}:
        duplicate = copy.deepcopy(next(event for event in sdk['events']
            if event.get('event', {}).get('method') == 'item/completed'
            and event['event']['params'].get('item', {}).get('id') == identity))
        duplicate['event']['params']['item']['id'] = 'additional-sdk-item'
        if mutation == 'extra':
            duplicate['event']['params']['item']['arguments']['query'] = 'unmatched additional operation'
        sdk['events'].insert(-1, duplicate)
    elif mutation == 'error':
        first['error'] = {'message': 'failed operation'}
    elif mutation == 'foreign-server':
        first['server'] = 'foreign-server'
    elif mutation == 'argument':
        first['arguments']['top_k'] = 6
    elif mutation == 'result':
        first['result']['content'][0]['text'] = 'Different returned discovery result'
    elif mutation == 'unknown-tool':
        first['tool'] = 'unreviewed_tool'
    else:
        first['status'] = 'inProgress'
    replace_sdk(source, sdk)
    inventory = capture_invocation_inventory(source)
    assert not inventory.closed
    external = capture_external_outputs(source, ExternalOutputSource())
    assert not external.closed
    assert {item.field: item.text for item in external.text_records} == {
        'assistant_name': 'Kevin Torres', 'assistant_email': 'kevin.torres@ironclad.example.com'}
    assert sdk_material(source)['mcp_item_execution_join'] == 'unqualified'


def test_two_indistinguishable_calls_on_both_sides_remain_coverage_ambiguous(original_source):
    source = copy.deepcopy(original_source)
    sdk = sdk_material(source)
    first, second = completed_calls(sdk)[:2]
    first_id, second_id = first['id'], second['id']
    for event in sdk['events']:
        item = event.get('event', {}).get('params', {}).get('item')
        if isinstance(item, dict) and item.get('id') == second_id:
            item['arguments'] = copy.deepcopy(first['arguments'])
            if event['event']['method'] == 'item/completed':
                item['result'] = copy.deepcopy(first['result'])
    originals = [json.loads(event['receipt_json']) for event in source['tool_execution_events']]
    first_terminal = next(item for item in originals if item['invocation_id'] == PAIRS[first_id]
        and item['phase'] == 'returned')
    for event in source['tool_execution_events']:
        receipt = json.loads(event['receipt_json'])
        if receipt['invocation_id'] != PAIRS[second_id]:
            continue
        receipt['arguments_json'] = first_terminal['arguments_json']
        if receipt['phase'] == 'returned':
            receipt['result_json'] = first_terminal['result_json']
            capture = json.loads(receipt['evidence_json'][0])
            capture['action']['arguments_json'] = canonical_json(json.loads(first_terminal['arguments_json'])['kwargs'])
            capture['action']['result_json'] = first_terminal['result_json']
            receipt['evidence_json'][0] = canonical_json(capture)
        event['receipt_json'] = canonical_json(receipt)
    replace_sdk(source, sdk)
    inventory = capture_invocation_inventory(source)
    assert len(inventory.entries) == 7 and all(entry.status == 'qualified' for entry in inventory.entries)
    assert not inventory.closed and 'ambiguous' in inventory.reason
    assert not capture_external_outputs(source, ExternalOutputSource()).closed


@pytest.mark.parametrize('mutation', ['missing-invocation', 'missing-return', 'missing-ack', 'extra-ack'])
def test_native_inventory_gaps_cannot_be_repaired_from_sdk_results(original_source, mutation):
    source = copy.deepcopy(original_source)
    identity = next(iter(PAIRS.values()))
    if mutation in {'missing-invocation', 'missing-return'}:
        source['tool_execution_events'] = [item for item in source['tool_execution_events']
            if not (json.loads(item['receipt_json'])['invocation_id'] == identity
                    and (mutation == 'missing-invocation' or json.loads(item['receipt_json'])['phase'] == 'returned'))]
    elif mutation == 'missing-ack':
        source['state_write_receipts'] = [item for item in source['state_write_receipts'] if item['write_id'] != identity]
    else:
        source['state_write_receipts'].append({**source['state_write_receipts'][0], 'write_id': 'unobserved-write'})
    assert not capture_invocation_inventory(source).closed
    assert not capture_external_outputs(source, ExternalOutputSource()).closed


def test_actual_external_projection_and_native_reload_preserve_original_archive():
    path, raw, envelope, episode, trace, task = actual()
    scalar, info = copy.deepcopy(trace.rewards), copy.deepcopy(trace.info)
    events, writes = tuple(trace.tool_execution_events), tuple(trace.state_write_receipts)
    source = material(trace, task)
    evidence = capture_external_outputs(source, ExternalOutputSource())
    assert evidence.closed and evidence.status == 'qualified'
    assert len(evidence.invocation_coverage) == 7
    assert len(evidence.text_records) == 2 and len(evidence.action_relations) == 2
    assert {item.field: item.text for item in evidence.text_records} == {
        'assistant_name': 'Kevin Torres', 'assistant_email': 'kevin.torres@ironclad.example.com'}
    assert all((item.invocation_id, item.surface, item.service, item.collection, item.record_id) == (
        '8baf7cd9ff6549b49fd1f565a59ad93a', 'record_field', 'salesforce', 'contacts', '003010')
        for item in evidence.text_records)
    assert {item.field: json.loads(item.value_json) for item in evidence.action_relations} == {
        'assistant_name': 'Kevin Torres', 'assistant_email': 'kevin.torres@ironclad.example.com'}
    assert all(item.changed and item.record_id == '003010' and item.service == 'salesforce'
        and item.collection == 'contacts' and item.invocation_id == '8baf7cd9ff6549b49fd1f565a59ad93a'
        for item in evidence.action_relations)
    assert [item.disposition for item in evidence.invocation_coverage].count('no_authored_fields') == 6
    assert [item.disposition for item in evidence.invocation_coverage].count('authored_fields') == 1
    validate_external_outputs(evidence, source, ExternalOutputSource())
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = AutomationBenchState(world=replay.info['automationbench']['end_state'],
        initial_state=task.data.initial_state, assertions=task.data.assertions,
        artifacts=read_retained_artifacts(path.parent, replay))
    restored = capture_external_outputs(material(replay, task), ExternalOutputSource())
    assert restored == evidence
    assert replay.rewards == scalar and trace.rewards == scalar and trace.info == info
    assert tuple(replay.tool_execution_events) == events and tuple(replay.state_write_receipts) == writes
    assert replay.info['codex_sdk']['mcp_item_execution_join'] == 'unqualified'
    assert path.read_bytes() == raw and (path.parent / 'trace-0-artifacts.json').read_bytes() == envelope


@pytest.mark.parametrize('mutation', ['text', 'relation', 'closure'])
def test_retained_projection_cannot_override_raw_external_source(original_source, mutation):
    evidence = capture_external_outputs(original_source, ExternalOutputSource())
    if mutation == 'text':
        forged = evidence.model_copy(update={'text_records': (evidence.text_records[0].model_copy(
            update={'text': 'Invented summary'}), *evidence.text_records[1:])})
    elif mutation == 'relation':
        forged = evidence.model_copy(update={'action_relations': (evidence.action_relations[0].model_copy(
            update={'record_id': 'foreign-contact'}), *evidence.action_relations[1:])})
    else:
        forged = evidence.model_copy(update={'closed': False, 'status': 'partial'})
    with pytest.raises(ValueError, match='raw_source_or_projection_mismatch'):
        validate_external_outputs(forged, original_source, ExternalOutputSource())
