"""Finite, source-bound semantic challenge preparation; never a policy evaluator.

Counterfactual receipts are explicitly manufactured fixture envelopes around
installed simulator calls, not observations of an agent or an MCP transport.
Expected labels belong to a separate review corpus and never enter preparation.
"""

import base64
import copy
import hashlib
import inspect
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictInt, StrictStr, TypeAdapter
from verifiers.v1.assessment_source import capture_trace_source, execution_refs
from verifiers.v1.mcp.execution import ToolServerReceipt
from verifiers.v1.trace import StateWriteReceipt, ToolServerExecutionEvent

from automationbench.schema.world import WorldState

from ..capture import CapturedAction, canonical_json
from ..contracts.authored_outputs import AuthoredOutputSource, capture_authored_outputs
from ..contracts.base import FrozenModel, Identifier
from ..contracts.engine import binding_reason, compile_contract
from ..contracts.external_outputs import ExternalOutputSource, capture_external_outputs
from ..contracts.invocation_inventory import capture_invocation_inventory
from ..contracts.models import ContractSpec, SourceBinding
from ..contracts.no_clarification import NoClarificationCheck, prepare_no_clarification_context
from ..contracts.summary_policy import (
    SummaryAssessor,
    SummaryExclusionCheck,
    SummaryPolicyContext,
    prepare_summary_context,
)
from ..manifest_assessments import ManifestAssessmentTask
from ..taskset import AutomationBenchData, AutomationBenchTaskConfig
from ..tools import AutomationBenchState, _registry
from .collector import read_retained_artifacts


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class ReplaceAssistant(FrozenModel):
    kind: Literal["replace_assistant_output"]
    selector: Identifier
    text: StrictStr


class RemoveAssistant(FrozenModel):
    kind: Literal["remove_assistant_output"]
    selector: Identifier


class InsertAssistant(FrozenModel):
    kind: Literal["insert_assistant_output"]
    output_alias: Identifier
    template: Identifier
    before: Identifier
    text: StrictStr


class ReplaceUserRequest(FrozenModel):
    kind: Literal["replace_user_request"]
    prompt_index: StrictInt = Field(ge=0)
    expected_text: StrictStr
    text: StrictStr


class DuplicateAssistant(FrozenModel):
    kind: Literal["duplicate_assistant_completion"]
    selector: Identifier
    text: StrictStr | None = None


class RemoveOperations(FrozenModel):
    kind: Literal["remove_all_operations"]


class OmitArtifact(FrozenModel):
    kind: Literal["omit_sdk_artifact"]
    logical_path: Literal["codex_sdk/events.json"]


class InitialText(FrozenModel):
    kind: Literal["initial_record_text"]
    selector: Identifier
    field: Identifier
    mode: Literal["append", "replace"]
    text: StrictStr


class InsertRecord(FrozenModel):
    kind: Literal["insert_initial_record"]
    service: Identifier
    collection: Identifier
    record: dict[str, Any]


class ReplaceArguments(FrozenModel):
    kind: Literal["replace_operation_arguments"]
    selector: Identifier
    arguments: dict[str, Any]


class InsertOperation(FrozenModel):
    kind: Literal["insert_operation"]
    after: Identifier
    operation_alias: Identifier
    outer_tool: Literal["execute_tool"]
    tool_name: Identifier
    arguments: dict[str, Any]


class OmitTerminal(FrozenModel):
    kind: Literal["omit_native_terminal_capture"]
    operation_alias: Identifier
    retain_sdk_observation: StrictBool


Transform = Annotated[
    ReplaceAssistant
    | RemoveAssistant
    | InsertAssistant
    | ReplaceUserRequest
    | DuplicateAssistant
    | RemoveOperations
    | OmitArtifact
    | InitialText
    | InsertRecord
    | ReplaceArguments
    | InsertOperation
    | OmitTerminal,
    Field(discriminator="kind"),
]


class AssistantTarget(FrozenModel):
    inventory: Literal["assistant"]
    selector: Identifier


class ExternalTarget(FrozenModel):
    inventory: Literal["external"]
    operation_alias: Identifier
    service: Identifier
    collection: Identifier
    record_id: Identifier | None
    field: Identifier


class SummaryCaseSpec(FrozenModel):
    case_id: Identifier
    evaluation_case_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    capture_mode: Literal["retained_actual", "manufactured_counterfactual"]
    transforms: tuple[Transform, ...]
    target: Annotated[AssistantTarget | ExternalTarget, Field(discriminator="inventory")] | None
    evaluation_output_alias: StrictStr | None


class UnsupportedCase(FrozenModel):
    case_id: Identifier
    evaluation_case_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    reason: StrictStr = Field(min_length=1)


class AssistantSelector(FrozenModel):
    kind: Literal["sdk_completed_agent_message"]
    item_id: Identifier
    expected_text: StrictStr
    expected_channel: StrictStr | None


class RecordSelector(FrozenModel):
    kind: Literal["initial_record"]
    service: Identifier
    collection: Identifier
    identity_field: Literal["id"]
    identity: Identifier
    expected_fields: dict[str, Any]


class OperationSelector(FrozenModel):
    kind: Literal["original_operation"]
    invocation_id: Identifier
    outer_tool: Literal["execute_tool"]
    tool_name: Identifier
    expected_arguments: dict[str, Any]


Selector = Annotated[
    AssistantSelector | RecordSelector | OperationSelector, Field(discriminator="kind")
]


class FrozenSummaryReplay(FrozenModel):
    source: vf.SourceSnapshot
    task_data_json: StrictStr
    task_config_json: StrictStr
    document_json: StrictStr
    sdk_json: StrictStr
    hydrated_initial_json: StrictStr
    provenance_json: StrictStr


class PreparedSummaryCase(FrozenModel):
    case_id: Identifier
    capture_mode: Literal["retained_actual", "manufactured_counterfactual"]
    case_digest: StrictStr
    source: vf.SourceSnapshot
    contract: ContractSpec
    view: vf.ObservationView
    context: SummaryPolicyContext
    target_output_key: StrictStr | None
    evaluation_output_alias: StrictStr | None
    task_data_json: StrictStr
    task_config_json: StrictStr
    provenance_json: StrictStr
    preparation_document_json: StrictStr
    spec_json: StrictStr


_SUMMARY = "summary_exclusions@1"
_CLARIFICATION = "no_clarification@1"
_CLARIFICATION_PROFILES = frozenset({_CLARIFICATION, "no_clarification@2"})
_ADDITIONAL_TOOLS = frozenset({"gmail_send_email"})


def _profile_document(document, profile):
    if (
        profile not in {_SUMMARY, *_CLARIFICATION_PROFILES}
        or document.get("policy_profile", _SUMMARY) != profile
    ):
        raise ValueError("summary_case_policy_profile_changed")
    tools = document.get("additional_reviewed_tools", [])
    if (
        type(tools) is not list
        or any(type(tool) is not str or tool not in _ADDITIONAL_TOOLS for tool in tools)
        or len(set(tools)) != len(tools)
        or (tools and profile not in _CLARIFICATION_PROFILES)
    ):
        raise ValueError("summary_case_reviewed_tools_unsupported")
    _unsupported(document, profile)
    return tuple(tools)


def _unsupported(document, profile):
    items = TypeAdapter(tuple[UnsupportedCase, ...]).validate_python(
        document.get("unsupported_cases", [])
    )
    if items and profile not in _CLARIFICATION_PROFILES:
        raise ValueError("summary_case_unsupported_accounting_requires_clarification")
    if len({item.case_id for item in items}) != len(items):
        raise ValueError("summary_case_unsupported_identity_duplicate")
    return items


def _verified_bytes(item):
    raw = Path(item["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("summary_case_original_file_digest_changed")
    return raw


def _safe(source):
    raw = json.loads(source.source_json)
    return {
        "task_evidence": raw["task_evidence"],
        "tool_execution_events": raw.get("tool_execution_events", []),
        "state_write_receipts": raw.get("state_write_receipts", []),
    }


def _canonical_view(source, contract, profile=_SUMMARY):
    subject = vf.SubjectRef(
        kind="trace",
        snapshot_id=source.snapshot_id,
        episode_id=source.episode_id,
        trace_id=json.loads(source.source_json)["trace_id"],
    )
    return vf.ObservationView.capture(
        {"source": _safe(source), "contract": contract.model_dump(mode="json")},
        snapshot_id=source.snapshot_id,
        builder_revision=(
            "automationbench.summary_cases@1"
            if profile == _SUMMARY
            else "automationbench.no_clarification_cases@1"
        ),
        scope="retrospective",
        subjects=(subject,),
    )


def _admit_config(config_json, provenance):
    # The inherited config loader converts JSON arrays before validation, so
    # strict JSON mode rejects valid tuple fields. Exact wire round-trip rejects
    # all coercions first; strict Python admission then checks the native value.
    config = AutomationBenchTaskConfig.model_validate_json(config_json)
    if (
        hashlib.sha256(config_json.encode()).hexdigest() != provenance["task_config_sha256"]
        or config.model_dump_json() != config_json
    ):
        raise ValueError("summary_case_prepared_task_config_changed")
    return AutomationBenchTaskConfig.model_validate(config.model_dump(mode="python"), strict=True)


def _one(items, reason):
    if len(items) != 1:
        raise ValueError(reason)
    return items[0]


def _record(initial, selector):
    rows = initial[selector.service][selector.collection]
    if not isinstance(rows, list):
        raise TypeError("summary_case_initial_collection_not_list")
    row = _one(
        [r for r in rows if r.get("id") == selector.identity],
        "summary_case_initial_record_ambiguous_or_absent",
    )
    if any(
        canonical_json(row.get(k)) != canonical_json(v) for k, v in selector.expected_fields.items()
    ):
        raise ValueError("summary_case_initial_record_changed")
    return row


def _selectors(document, raw):
    selectors = TypeAdapter(dict[str, Selector]).validate_python(document["selectors"])
    authored = capture_authored_outputs(raw, AuthoredOutputSource())
    inventory = capture_invocation_inventory(raw)
    for selector in selectors.values():
        if isinstance(selector, AssistantSelector):
            output = _one(
                [o for o in authored.records if o.output_id == selector.item_id],
                "summary_case_original_output_ambiguous_or_absent",
            )
            if (output.text, output.channel) != (selector.expected_text, selector.expected_channel):
                raise ValueError("summary_case_original_output_changed")
        elif isinstance(selector, RecordSelector):
            _record(raw["task_evidence"]["initial"], selector)
        else:
            entry = _one(
                [e for e in inventory.entries if e.invocation_id == selector.invocation_id],
                "summary_case_original_operation_ambiguous_or_absent",
            )
            expected = {
                "tool_name": selector.tool_name,
                "arguments": canonical_json(selector.expected_arguments),
            }
            if entry.outer_arguments_json is None:
                raise ValueError("summary_case_original_arguments_missing")
            kwargs = json.loads(entry.outer_arguments_json)
            if (
                entry.status != "qualified"
                or entry.outer_tool != selector.outer_tool
                or kwargs.get("tool_name") != expected["tool_name"]
                or canonical_json(json.loads(kwargs.get("arguments", "null")))
                != canonical_json(selector.expected_arguments)
            ):
                raise ValueError("summary_case_original_operation_changed")
    return selectors


def _load_replay(document: Mapping, *, profile) -> FrozenSummaryReplay:
    """Verify immutable inputs and hydrate once, before detached case preparation."""
    document = json.loads(canonical_json(document))
    _profile_document(document, profile)
    corpus = json.loads(_verified_bytes(document["corpus"]))
    cases = TypeAdapter(tuple[SummaryCaseSpec, ...]).validate_python(document["cases"])
    unsupported = _unsupported(document, profile)
    original = {item["case_id"]: item for item in corpus["cases"]}
    runnable_ids, unsupported_ids = (
        {case.case_id for case in cases},
        {case.case_id for case in unsupported},
    )
    if (
        len(runnable_ids) != len(cases)
        or runnable_ids & unsupported_ids
        or set(original) != runnable_ids | unsupported_ids
    ):
        raise ValueError("summary_case_corpus_population_changed")
    for case in unsupported:
        if case.evaluation_case_sha256 != _digest(original[case.case_id]):
            raise ValueError("summary_case_unsupported_review_anchor_changed")
    for case in cases:
        if case.evaluation_case_sha256 != _digest(original[case.case_id]):
            raise ValueError("summary_case_reviewed_recipe_anchor_changed")
        reviewed = original[case.case_id]
        actual = reviewed["provenance"] == "retained_actual_output"
        output = reviewed["output"]
        if (
            actual != (case.capture_mode == "retained_actual")
            or (case.target is None) != (output is None)
            or case.evaluation_output_alias != (output["output_id"] if output else None)
        ):
            raise ValueError("summary_case_reviewed_target_or_provenance_changed")
        if case.capture_mode == "retained_actual" and case.transforms:
            raise ValueError("summary_case_actual_cannot_transform")
    baseline = document["baseline"]
    episode = vf.WireEpisode.model_validate_json(_verified_bytes(baseline["episode"]))
    _verified_bytes(baseline["artifact_envelope"])
    trace = cast(
        Any,
        _one(
            [t for t in episode.traces if t.id == baseline["trace_id"]],
            "summary_case_original_trace_ambiguous_or_absent",
        ),
    )
    artifacts = read_retained_artifacts(Path(baseline["episode"]["path"]).parent, trace)
    sdk = artifacts[baseline["sdk_artifact"]["logical_path"]]
    if (
        not isinstance(sdk, bytes)
        or hashlib.sha256(sdk).hexdigest() != baseline["sdk_artifact"]["sha256"]
    ):
        raise ValueError("summary_case_original_sdk_changed")
    data = AutomationBenchData.model_validate(trace.task.data.model_dump(mode="json"))
    config = AutomationBenchTaskConfig(capture_actions=True)
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=(),
        artifacts=artifacts,
    )
    task = ManifestAssessmentTask(data, config)
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    raw = _safe(source)
    policy = raw
    for part in document["policy"]["path"]:
        policy = policy[part]
    if (
        _digest(policy) != document["policy"]["canonical_json_sha256"]
        or document["policy"]["transforms_allowed"] is not False
    ):
        raise ValueError("summary_case_original_public_policy_changed")
    _selectors(document, raw)
    inventory = capture_invocation_inventory(raw)
    if not inventory.closed or not inventory.entries or inventory.entries[0].before_json is None:
        raise ValueError("summary_case_baseline_invocation_capture_unavailable")
    return FrozenSummaryReplay(
        source=source,
        task_data_json=data.model_dump_json(),
        task_config_json=config.model_dump_json(),
        document_json=canonical_json(document),
        sdk_json=sdk.decode(),
        hydrated_initial_json=inventory.entries[0].before_json,
        provenance_json=canonical_json(
            {
                "original": baseline,
                "corpus_sha256": document["corpus"]["sha256"],
                "preparation_document_digest": _digest(document),
                "baseline_source_digest": source.source_digest,
                "task_config_sha256": hashlib.sha256(config.model_dump_json().encode()).hexdigest(),
            }
        ),
    )


def load_summary_replay(document: Mapping) -> FrozenSummaryReplay:
    return _load_replay(document, profile=_SUMMARY)


def _sdk_event(method, thread, turn_id, **params):
    return {
        "kind": "event",
        "event": {"method": method, "params": {"threadId": thread, "turnId": turn_id, **params}},
    }


def _replace_sdk(raw, sdk):
    encoded = canonical_json(sdk).encode()
    projection = raw["task_evidence"]["authored_outputs"]
    projection.update(
        sdk_info=sdk,
        sdk_artifact_base64=base64.b64encode(encoded).decode(),
        sdk_artifact_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    raw["artifacts"]["codex_sdk/events.json"] = hashlib.sha256(encoded).hexdigest()


def _edit_assistant(sdk, selector, text, identity):
    events = []
    found = 0
    for original in sdk["events"]:
        event = copy.deepcopy(original)
        params = event.get("event", {}).get("params", {})
        method = event.get("event", {}).get("method")
        if method in {"rawResponse/completed", "thread/tokenUsage/updated"}:
            continue  # Original usage is not a measurement of modified text.
        if method == "item/agentMessage/delta" and params.get("itemId") == selector.item_id:
            continue
        item = params.get("item")
        if isinstance(item, dict) and item.get("id") == selector.item_id:
            if method == "item/completed":
                found += 1
            if text is None:
                continue
            item.update(id=identity, text=text)
        turn = params.get("turn")
        if isinstance(turn, dict) and isinstance(turn.get("items"), list):
            replaced = []
            for item in turn["items"]:
                if item.get("id") == selector.item_id:
                    if text is None:
                        continue
                    item.update(id=identity, text=text)
                replaced.append(item)
            turn["items"] = replaced
        events.append(event)
    if found != 1:
        raise ValueError("summary_case_sdk_output_resolution_changed")
    sdk["events"] = events


def _insert_assistant(sdk, transform, selectors, alias_ids, output_ids, prefix):
    template = selectors.get(transform.template)
    if (
        not isinstance(template, AssistantSelector)
        or transform.output_alias in output_ids
        or transform.output_alias in selectors
    ):
        raise ValueError("summary_case_insert_output_template_or_alias_invalid")
    if transform.before in alias_ids:
        invocation = alias_ids[transform.before]
        if not invocation.startswith(prefix + "-invocation-"):
            raise ValueError("summary_case_insert_output_requires_replayed_operation")
        anchor = prefix + "-call-" + invocation.removeprefix(prefix + "-invocation-")
        phase = "item/started"
    elif transform.before in output_ids:
        anchor, phase = output_ids[transform.before], "item/completed"
    else:
        raise ValueError("summary_case_insert_output_anchor_unavailable")
    positions = [
        index
        for index, event in enumerate(sdk["events"])
        if event.get("event", {}).get("method") == phase
        and event.get("event", {}).get("params", {}).get("item", {}).get("id") == anchor
    ]
    position = _one(positions, "summary_case_insert_output_anchor_ambiguous")
    params = sdk["events"][position]["event"]["params"]
    identity = prefix + "-assistant-" + transform.output_alias
    item = {"type": "agentMessage", "id": identity, "text": transform.text}
    if template.expected_channel is not None:
        item["channel"] = template.expected_channel
    sdk["events"].insert(
        position, _sdk_event("item/completed", params["threadId"], params["turnId"], item=item)
    )
    output_ids[transform.output_alias] = identity


def _duplicate_assistant(sdk, output_id, text):
    position = _one(
        [
            index
            for index, event in enumerate(sdk["events"])
            if event.get("event", {}).get("method") == "item/completed"
            and event.get("event", {}).get("params", {}).get("item", {}).get("id") == output_id
        ],
        "summary_case_duplicate_output_unavailable",
    )
    duplicate = copy.deepcopy(sdk["events"][position])
    item = duplicate["event"]["params"]["item"]
    if item.get("type") != "agentMessage":
        raise ValueError("summary_case_duplicate_output_requires_agent_message")
    if text is not None:
        item["text"] = text
    sdk["events"].insert(position + 1, duplicate)


def _insert_record(initial, transform):
    # Only installed typed record collections: no raw dictionary/custom ontology.
    world = WorldState.model_validate(initial)
    service = getattr(world, transform.service, None)
    rows = getattr(service, transform.collection, None)
    definition = (
        type(service).model_fields.get(transform.collection) if service is not None else None
    )
    from typing import get_args, get_origin

    from pydantic import BaseModel

    if (
        definition is None
        or get_origin(definition.annotation) is not list
        or not isinstance(rows, list)
    ):
        raise ValueError("summary_case_insert_requires_native_typed_collection")
    types = get_args(definition.annotation)
    if len(types) != 1 or not isinstance(types[0], type) or not issubclass(types[0], BaseModel):
        raise ValueError("summary_case_insert_requires_native_record_model")
    record_type = types[0]
    identity = transform.record.get("id")
    if (
        type(identity) is not str
        or not identity
        or any(row.id == identity for row in rows)
        or set(transform.record) - set(record_type.model_fields)
    ):
        raise ValueError("summary_case_insert_identity_or_fields_invalid")
    record_type.model_validate(transform.record, strict=True)
    initial[transform.service][transform.collection].append(copy.deepcopy(transform.record))


def _replay(baseline, spec, raw, selectors, prefix, additional_tools=()):
    inventory = capture_invocation_inventory(_safe(baseline.source))
    aliases = {
        s.invocation_id: key for key, s in selectors.items() if isinstance(s, OperationSelector)
    }
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for entry in inventory.entries:
        if entry.outer_tool is None or entry.outer_arguments_json is None:
            raise ValueError("summary_case_replay_original_arguments_unavailable")
        operations.append(
            (
                aliases.get(entry.invocation_id, entry.invocation_id),
                entry.outer_tool,
                json.loads(entry.outer_arguments_json),
            )
        )
    initial = copy.deepcopy(raw["task_evidence"]["initial"])
    hydrated = json.loads(baseline.hydrated_initial_json)
    omitted = set()
    inserted_after = {}
    if any(isinstance(t, RemoveOperations) for t in spec.transforms):
        if sum(isinstance(t, RemoveOperations) for t in spec.transforms) != 1 or any(
            isinstance(t, (ReplaceArguments, InsertOperation, OmitTerminal))
            for t in spec.transforms
        ):
            raise ValueError("summary_case_remove_operations_conflicting_transform")
        operations = []
    for transform in spec.transforms:
        if isinstance(transform, InitialText):
            selector = selectors[transform.selector]
            if (
                not isinstance(selector, RecordSelector)
                or transform.field not in selector.expected_fields
            ):
                raise ValueError("summary_case_text_requires_reviewed_original_field")
            for target in (initial, hydrated):
                row = _record(target, selector)
                before = row[transform.field]
                if type(before) is not str:
                    raise TypeError("summary_case_text_field_not_text")
                row[transform.field] = (
                    before + transform.text if transform.mode == "append" else transform.text
                )
        elif isinstance(transform, InsertRecord):
            _insert_record(initial, transform)
            _insert_record(hydrated, transform)
        elif isinstance(transform, ReplaceArguments):
            selector = selectors[transform.selector]
            if not isinstance(selector, OperationSelector):
                raise TypeError("summary_case_operation_selector_invalid")
            operations = [
                (
                    alias,
                    outer,
                    {
                        "tool_name": selector.tool_name,
                        "arguments": canonical_json(transform.arguments),
                    }
                    if alias == transform.selector
                    else args,
                )
                for alias, outer, args in operations
            ]
        elif isinstance(transform, InsertOperation):
            names = [alias for alias, _, _ in operations]
            if transform.operation_alias in names or transform.after not in names:
                raise ValueError("summary_case_insert_operation_anchor_invalid")
            anchor = inserted_after.get(transform.after, transform.after)
            position = names.index(anchor) + 1
            operations.insert(
                position,
                (
                    transform.operation_alias,
                    transform.outer_tool,
                    {
                        "tool_name": transform.tool_name,
                        "arguments": canonical_json(transform.arguments),
                    },
                ),
            )
            inserted_after[transform.after] = transform.operation_alias
        elif isinstance(transform, OmitTerminal):
            if not transform.retain_sdk_observation or transform.operation_alias in omitted:
                raise ValueError("summary_case_capture_gap_invalid")
            omitted.add(transform.operation_alias)
    if not omitted <= {alias for alias, _, _ in operations}:
        raise ValueError("summary_case_capture_gap_unknown_operation")
    world = WorldState.model_validate(hydrated)
    events, writes, results, handler_sources, alias_ids = [], [], [], {}, {}
    registry = _registry()
    allowed = set(json.loads(baseline.task_data_json)["zapier_tools"]) | set(additional_tools)
    for index, (alias, outer, args) in enumerate(operations):
        before = canonical_json(world.model_dump(mode="json"))
        if outer == "search_tools":
            result = json.dumps(
                registry.bm25(args["query"], top_k=max(1, min(args.get("top_k", 5), 20))), indent=2
            )
            handler = type(registry).bm25
        elif outer == "execute_tool" and args["tool_name"] in allowed:
            result = registry.execute(args["tool_name"], args["arguments"], world=world)
            handler = registry._tool_map[args["tool_name"]]
        else:
            raise ValueError("summary_case_operation_outside_original_installed_tools")
        filename = inspect.getsourcefile(handler)
        if filename is None:
            raise ValueError("summary_case_handler_source_unavailable")
        handler_sources[handler.__module__ + "." + handler.__qualname__] = hashlib.sha256(
            Path(filename).read_bytes()
        ).hexdigest()
        after = canonical_json(world.model_dump(mode="json"))
        before_digest, after_digest = (
            hashlib.sha256(before.encode()).hexdigest(),
            hashlib.sha256(after.encode()).hexdigest(),
        )
        action = CapturedAction(
            occurrence_index=index,
            tool_name=outer,
            arguments_json=canonical_json(args),
            before_digest=before_digest,
            after_digest=after_digest,
            status="returned",
            result_json=canonical_json(result),
        )
        evidence = canonical_json(
            {
                "kind": "automationbench_raw_action",
                "action": action.model_dump(mode="json"),
                "snapshots": {before_digest: before, after_digest: after},
            }
        )
        invocation = f"{prefix}-invocation-{index}"
        alias_ids[alias] = invocation
        identity = {
            "invocation_id": invocation,
            "tool_name": outer,
            "arguments_json": canonical_json({"args": [], "kwargs": args}),
            "state_read_revision": index,
        }
        dispatch = ToolServerReceipt(**identity, event_index=0, phase="dispatch")
        terminal = ToolServerReceipt(
            **identity,
            event_index=1,
            phase="returned",
            evidence_json=(evidence,),
            result_json=canonical_json(result),
            state_write_revision=index + 1,
            state_conflict=False,
            state_persistence="applied",
        )
        for receipt in (dispatch,) if alias in omitted else (dispatch, terminal):
            events.append(
                ToolServerExecutionEvent(
                    invocation_id=invocation,
                    event_index=receipt.event_index,
                    phase=receipt.phase,
                    receipt_seq=len(events),
                    state_revision=index if receipt.phase == "dispatch" else index + 1,
                    receipt_json=canonical_json(receipt.model_dump(mode="json")),
                ).model_dump(mode="json")
            )
        if alias not in omitted:
            writes.append(
                StateWriteReceipt(
                    write_id=invocation,
                    body_digest=after_digest,
                    expected_revision=index,
                    applied_revision=index + 1,
                    conflict=False,
                ).model_dump(mode="json")
            )
        results.append((outer, args, result))
    # A declared zero-step counterfactual is the identity on the public state.
    # Do not present newly constructed defaults as observed episode mutations.
    zero_step = any(isinstance(t, RemoveOperations) for t in spec.transforms)
    if zero_step and (operations or events or writes or results):
        raise ValueError("summary_case_zero_step_has_operations")
    raw["task_evidence"].update(
        initial=initial,
        final=copy.deepcopy(initial) if zero_step else world.model_dump(mode="json"),
    )
    raw.update(
        tool_execution_events=events,
        state_write_receipts=writes,
        tool_state_revision=len(operations),
    )
    raw["task"]["data"]["initial_state"] = copy.deepcopy(initial)
    return results, alias_ids, handler_sources


def _fixture_sdk(baseline, results, prefix):
    template = json.loads(baseline.sdk_json)
    aliases = template["server_aliases"]
    server = aliases[""]
    thread, turn = prefix + "-thread", prefix + "-turn"
    # Only route capabilities are inherited; all lifecycle records are fixtures.
    events = [
        {
            "kind": "mcp_inventory",
            "scope": "thread_bound",
            "servers": [
                {
                    "name": server,
                    "runtime_status": "connected",
                    "tool_names": template["approved_mcp_tools"][server],
                }
            ],
        }
    ]
    for index, (outer, args, result) in enumerate(results):
        for phase in ("started", "completed"):
            item = {
                "type": "mcpToolCall",
                "id": f"{prefix}-call-{index}",
                "server": server,
                "tool": outer,
                "arguments": args,
                "status": "inProgress" if phase == "started" else "completed",
                "error": None,
                "result": None
                if phase == "started"
                else {
                    "content": [{"type": "text", "text": result}],
                    "structuredContent": {"result": result},
                },
            }
            events.append(_sdk_event("item/" + phase, thread, turn, item=item))
    originals = capture_authored_outputs(_safe(baseline.source), AuthoredOutputSource()).records
    for output in originals:
        item = {"type": "agentMessage", "id": output.output_id, "text": output.text}
        if output.channel is not None:
            item["channel"] = output.channel
        events.append(
            _sdk_event(
                "item/completed",
                thread,
                turn,
                item=item,
            )
        )
    events.extend(
        [
            _sdk_event(
                "turn/completed",
                thread,
                turn,
                turn={"id": turn, "status": "completed", "error": None, "items": []},
            ),
            {
                "kind": "finished",
                "ok": True,
                "status": "completed",
                "thread_id": thread,
                "turn_id": turn,
            },
        ]
    )
    return {
        "events": events,
        "server_aliases": aliases,
        "approved_mcp_tools": template["approved_mcp_tools"],
        "mcp_item_execution_join": "unqualified",
    }


def _context(source, contract, profile=_SUMMARY):
    check = contract.checks[0]
    expected = SummaryExclusionCheck if profile == _SUMMARY else NoClarificationCheck
    if (
        not isinstance(check, expected)
        or check.operator != profile
        or len(contract.checks) != 1
        or contract.credit
    ):
        raise ValueError("summary_case_contract_scope_changed")
    raw = _safe(source)
    reason = binding_reason(raw, contract)
    if reason is not None:
        raise ValueError(reason)
    a, e = AuthoredOutputSource(), ExternalOutputSource()
    prepare = prepare_summary_context if profile == _SUMMARY else prepare_no_clarification_context
    return prepare(
        raw,
        cast(Any, check),
        capture_authored_outputs(raw, a),
        capture_external_outputs(raw, e, native_source=source),
        assistant_source=a,
        external_source=e,
        native_source=source,
    )


def _prepare_case(
    baseline: FrozenSummaryReplay,
    spec: SummaryCaseSpec,
    *,
    assessor: SummaryAssessor | None = None,
    profile,
) -> PreparedSummaryCase:
    """Prepare one detached fixture; no solver, assessor or credit execution."""
    baseline = FrozenSummaryReplay.model_validate(baseline.model_dump(mode="python"))
    spec = SummaryCaseSpec.model_validate(spec.model_dump(mode="python"))
    document = json.loads(baseline.document_json)
    additional_tools = _profile_document(document, profile)
    provenance_anchor = json.loads(baseline.provenance_json)
    _admit_config(baseline.task_config_json, provenance_anchor)
    if (
        provenance_anchor["preparation_document_digest"] != _digest(document)
        or provenance_anchor["baseline_source_digest"] != baseline.source.source_digest
    ):
        raise ValueError("summary_case_frozen_baseline_changed")
    original_material = _safe(baseline.source)
    original_inventory = capture_invocation_inventory(original_material)
    if (
        not original_inventory.closed
        or not original_inventory.entries
        or original_inventory.entries[0].before_json != baseline.hydrated_initial_json
        or hashlib.sha256(baseline.sdk_json.encode()).hexdigest()
        != document["baseline"]["sdk_artifact"]["sha256"]
    ):
        raise ValueError("summary_case_frozen_capture_changed")
    original_data = json.loads(baseline.task_data_json)
    if any(
        canonical_json(original_data[key])
        != canonical_json(original_material["task_evidence"][other])
        for key, other in (
            ("prompt", "prompt"),
            ("initial_state", "initial"),
            ("task_name", "task_name"),
        )
    ):
        raise ValueError("summary_case_frozen_task_data_changed")
    declared = _one(
        [c for c in document["cases"] if c["case_id"] == spec.case_id],
        "summary_case_spec_not_declared",
    )
    if SummaryCaseSpec.model_validate(declared) != spec:
        raise ValueError("summary_case_spec_changed_after_review")
    raw = json.loads(baseline.source.source_json)
    selectors = _selectors(document, _safe(baseline.source))
    spec_digest = _digest(spec.model_dump(mode="json"))
    prefix = "fixture-" + spec_digest[:24]
    alias_ids = {
        key: s.invocation_id for key, s in selectors.items() if isinstance(s, OperationSelector)
    }
    output_ids = {
        key: s.item_id for key, s in selectors.items() if isinstance(s, AssistantSelector)
    }
    handler_sources = {}
    for transform in spec.transforms:
        if isinstance(transform, ReplaceUserRequest):
            for prompt in (raw["task_evidence"]["prompt"], raw["task"]["data"]["prompt"]):
                if transform.prompt_index >= len(prompt):
                    raise ValueError("summary_case_user_request_index_unavailable")
                message = prompt[transform.prompt_index]
                if (
                    message.get("role") != "user"
                    or message.get("content") != transform.expected_text
                ):
                    raise ValueError("summary_case_user_request_source_changed")
                message["content"] = transform.text
    replay = any(
        isinstance(
            t,
            (
                InitialText,
                InsertRecord,
                ReplaceArguments,
                InsertOperation,
                OmitTerminal,
                InsertAssistant,
                RemoveOperations,
            ),
        )
        for t in spec.transforms
    )
    if replay:
        results, alias_ids, handler_sources = _replay(
            baseline, spec, raw, selectors, prefix, additional_tools
        )
        sdk = _fixture_sdk(baseline, results, prefix)
    else:
        sdk = json.loads(baseline.sdk_json)
    for transform in spec.transforms:
        if isinstance(transform, (ReplaceAssistant, RemoveAssistant)):
            selector = selectors[transform.selector]
            if not isinstance(selector, AssistantSelector):
                raise TypeError("summary_case_assistant_selector_invalid")
            identity = prefix + "-assistant-" + transform.selector
            _edit_assistant(
                sdk,
                selector,
                transform.text if isinstance(transform, ReplaceAssistant) else None,
                identity,
            )
            output_ids[transform.selector] = identity
        elif isinstance(transform, InsertAssistant):
            _insert_assistant(sdk, transform, selectors, alias_ids, output_ids, prefix)
    if replay:
        # Even inherited text in a replay is a manufactured SDK observation.
        changed = {
            t.selector
            for t in spec.transforms
            if isinstance(t, (ReplaceAssistant, RemoveAssistant))
        }
        for alias, selector in selectors.items():
            if isinstance(selector, AssistantSelector) and alias not in changed:
                identity = prefix + "-assistant-" + alias
                _edit_assistant(sdk, selector, selector.expected_text, identity)
                output_ids[alias] = identity
    for index, transform in enumerate(spec.transforms):
        if isinstance(transform, DuplicateAssistant):
            if any(
                isinstance(t, (ReplaceAssistant, RemoveAssistant))
                and t.selector == transform.selector
                for t in spec.transforms[index + 1 :]
            ):
                raise ValueError("summary_case_duplicate_output_requires_final_text")
            if transform.selector not in output_ids:
                raise ValueError("summary_case_duplicate_output_selector_unavailable")
            _duplicate_assistant(sdk, output_ids[transform.selector], transform.text)
    if spec.capture_mode == "retained_actual":
        if spec.transforms:
            raise ValueError("summary_case_actual_cannot_transform")
        source = baseline.source
    else:
        raw["trace_id"] = prefix + "-trace"
        if additional_tools:
            raw["task"]["data"]["zapier_tools"] = list(
                dict.fromkeys([*raw["task"]["data"]["zapier_tools"], *additional_tools])
            )
        raw["task_evidence"]["authored_outputs"]["trace_id"] = raw["trace_id"]
        _replace_sdk(raw, sdk)
        if any(isinstance(t, OmitArtifact) for t in spec.transforms):
            raw["task_evidence"]["authored_outputs"].update(
                sdk_artifact_base64=None, sdk_artifact_sha256=None
            )
            raw["artifacts"].pop("codex_sdk/events.json", None)
        source = vf.SourceSnapshot.capture(
            raw,
            episode_id=prefix + "-episode",
            trace_ids=(raw["trace_id"],),
            nodes=(),
            executions=execution_refs(
                raw, episode_id=prefix + "-episode", trace_id=raw["trace_id"]
            ),
        )
    safe = _safe(source)
    policy = document["policy"]
    value = safe
    for part in policy["path"]:
        value = value[part]
    if _digest(value) != policy["canonical_json_sha256"]:
        raise ValueError("summary_case_policy_changed")
    check_type = SummaryExclusionCheck if profile == _SUMMARY else NoClarificationCheck
    check = check_type.model_validate(
        {
            "operator": profile,
            "check_id": "summary-policy" if profile == _SUMMARY else "no-clarification-policy",
            "signal_id": "summary.exclusions"
            if profile == _SUMMARY
            else "clarification.compliance",
            "source": "assistant",
            "external": "external",
            "policy_path": tuple(policy["path"]),
            "policy_digest": policy["canonical_json_sha256"],
            "assessor": assessor,
        }
    )
    contract = ContractSpec(
        schema_version=1,
        manifest_id="summary-semantic-preparation"
        if profile == _SUMMARY
        else "no-clarification-semantic-preparation",
        revision="2" if profile == "no_clarification@2" else "1",
        public_request=(
            "Assess the retained public summary-exclusion policy in the full observed action context."
            if profile == _SUMMARY
            else "Assess the retained public no-clarification policy in the full observed action context."
        ),
        bindings=tuple(
            SourceBinding(
                path=("task_evidence", key), canonical_sha256=_digest(safe["task_evidence"][key])
            )
            for key in ("prompt", "initial")
        ),
        sources={"assistant": AuthoredOutputSource(), "external": ExternalOutputSource()},
        checks=(check,),
        credit=(),
    )
    compile_contract(contract)
    context = _context(source, contract, profile)
    view = _canonical_view(source, contract, profile)
    target = None
    if isinstance(spec.target, AssistantTarget):
        target = _one(
            [
                o
                for o in context.outputs
                if o.inventory == "assistant" and o.output_id == output_ids[spec.target.selector]
            ],
            "summary_case_target_unresolved",
        ).output_key
    elif isinstance(spec.target, ExternalTarget):
        target_spec = spec.target

        def matches(output):
            fact = json.loads(output.fact_json)
            return (
                output.inventory == "external"
                and all(
                    fact.get(k) == v
                    for k, v in {
                        "invocation_id": alias_ids[target_spec.operation_alias],
                        "service": target_spec.service,
                        "collection": target_spec.collection,
                        "field": target_spec.field,
                    }.items()
                )
                and (
                    target_spec.record_id is None or fact.get("record_id") == target_spec.record_id
                )
            )

        target = _one(
            [o for o in context.outputs if matches(o)], "summary_case_target_unresolved"
        ).output_key
    task_data = json.loads(baseline.task_data_json)
    task_data["prompt"] = safe["task_evidence"]["prompt"]
    task_data["initial_state"] = safe["task_evidence"]["initial"]
    if spec.capture_mode != "retained_actual" and additional_tools:
        task_data["zapier_tools"] = list(
            dict.fromkeys([*task_data["zapier_tools"], *additional_tools])
        )
    task_data["assertions"] = []  # Hidden benchmark assertions are never challenge authority.
    provenance = json.loads(baseline.provenance_json) | {
        "case_digest": spec_digest,
        "evaluation_case_sha256": spec.evaluation_case_sha256,
        "capture_mode": spec.capture_mode,
        "transforms": [t.model_dump(mode="json") for t in spec.transforms],
        "handler_source_sha256": handler_sources,
        "native_capture": "manufactured" if replay else "retained_actual",
        "sdk_capture": "retained_actual" if not spec.transforms else "manufactured_counterfactual",
        "alias_invocations": alias_ids,
        "source_digest": source.source_digest,
        "context_digest": context.context_digest,
        "target_output_key": target,
        "transport_qualification": False,
    }
    if any(isinstance(t, RemoveOperations) for t in spec.transforms):
        provenance["zero_operation_identity_transition"] = {
            "derivation": "zero_operations_preserve_declared_initial_state",
            "observed_hydrated_world": False,
        }
    return PreparedSummaryCase(
        case_id=spec.case_id,
        capture_mode=spec.capture_mode,
        case_digest=spec_digest,
        source=source,
        contract=contract,
        view=view,
        context=context,
        target_output_key=target,
        evaluation_output_alias=spec.evaluation_output_alias,
        task_data_json=canonical_json(task_data),
        task_config_json=baseline.task_config_json,
        provenance_json=canonical_json(provenance),
        preparation_document_json=baseline.document_json,
        spec_json=canonical_json(spec.model_dump(mode="json")),
    )


def prepare_summary_case(
    baseline: FrozenSummaryReplay, spec: SummaryCaseSpec, *, assessor: SummaryAssessor | None = None
) -> PreparedSummaryCase:
    return _prepare_case(baseline, spec, assessor=assessor, profile=_SUMMARY)


def prepare_summary_cases(
    document: Mapping, *, assessor: SummaryAssessor | None = None
) -> tuple[PreparedSummaryCase, ...]:
    baseline = load_summary_replay(document)
    return tuple(
        prepare_summary_case(baseline, SummaryCaseSpec.model_validate(spec), assessor=assessor)
        for spec in document["cases"]
    )


def _validate_prepared_case(prepared: PreparedSummaryCase, *, profile) -> PreparedSummaryCase:
    """Re-admit a frozen prepared artifact before runner scheduling, without a judge."""
    prepared = PreparedSummaryCase.model_validate(prepared.model_dump(mode="python"))
    document = json.loads(prepared.preparation_document_json)
    additional_tools = _profile_document(document, profile)
    spec = SummaryCaseSpec.model_validate_json(prepared.spec_json)
    declared = _one(
        [c for c in document["cases"] if c["case_id"] == spec.case_id],
        "summary_case_spec_not_declared",
    )
    provenance = json.loads(prepared.provenance_json)
    _admit_config(prepared.task_config_json, provenance)
    if (
        SummaryCaseSpec.model_validate(declared) != spec
        or _digest(spec.model_dump(mode="json")) != prepared.case_digest
        or spec.case_id != prepared.case_id
        or spec.capture_mode != prepared.capture_mode
        or spec.evaluation_output_alias != prepared.evaluation_output_alias
        or provenance["case_digest"] != prepared.case_digest
        or provenance["preparation_document_digest"] != _digest(document)
        or provenance["source_digest"] != prepared.source.source_digest
        or provenance["target_output_key"] != prepared.target_output_key
    ):
        raise ValueError("summary_case_prepared_review_identity_changed")
    if prepared.capture_mode == "retained_actual" and (
        spec.transforms or provenance["baseline_source_digest"] != prepared.source.source_digest
    ):
        raise ValueError("summary_case_actual_source_changed")
    context = _context(prepared.source, prepared.contract, profile)
    if any(isinstance(t, RemoveOperations) for t in spec.transforms):
        material = json.loads(prepared.source.source_json)
        if (
            prepared.capture_mode != "manufactured_counterfactual"
            or material.get("tool_execution_events") != []
            or material.get("state_write_receipts") != []
            or type(material.get("tool_state_revision")) is not int
            or material["tool_state_revision"] != 0
            or canonical_json(material["task_evidence"]["initial"])
            != canonical_json(material["task_evidence"]["final"])
            or context.invocations
            or provenance.get("zero_operation_identity_transition")
            != {
                "derivation": "zero_operations_preserve_declared_initial_state",
                "observed_hydrated_world": False,
            }
        ):
            raise ValueError("summary_case_zero_step_identity_changed")
    if context != prepared.context:
        raise ValueError("summary_case_prepared_context_changed")
    if prepared.view != _canonical_view(prepared.source, prepared.contract, profile):
        raise ValueError("summary_case_prepared_view_changed")
    selectors = TypeAdapter(dict[str, Selector]).validate_python(document["selectors"])
    if isinstance(spec.target, AssistantTarget):
        selector = selectors.get(spec.target.selector)
        inserted = [
            t
            for t in spec.transforms
            if isinstance(t, InsertAssistant) and t.output_alias == spec.target.selector
        ]
        if not isinstance(selector, AssistantSelector) and len(inserted) != 1:
            raise TypeError("summary_case_target_selector_invalid")
        changed = any(
            isinstance(
                t,
                (
                    InitialText,
                    InsertRecord,
                    ReplaceArguments,
                    InsertOperation,
                    OmitTerminal,
                    InsertAssistant,
                    RemoveOperations,
                ),
            )
            for t in spec.transforms
        ) or any(
            isinstance(t, ReplaceAssistant) and t.selector == spec.target.selector
            for t in spec.transforms
        )
        output_id = (
            "fixture-" + prepared.case_digest[:24] + "-assistant-" + spec.target.selector
            if changed
            else cast(AssistantSelector, selector).item_id
        )
        target = _one(
            [o for o in context.outputs if o.inventory == "assistant" and o.output_id == output_id],
            "summary_case_prepared_target_changed",
        ).output_key
    elif isinstance(spec.target, ExternalTarget):
        target_spec = spec.target

        def match(output):
            fact = json.loads(output.fact_json)
            return (
                output.inventory == "external"
                and all(
                    fact.get(k) == v
                    for k, v in {
                        "invocation_id": provenance["alias_invocations"][
                            target_spec.operation_alias
                        ],
                        "service": target_spec.service,
                        "collection": target_spec.collection,
                        "field": target_spec.field,
                    }.items()
                )
                and (
                    target_spec.record_id is None or fact.get("record_id") == target_spec.record_id
                )
            )

        target = _one(
            [o for o in context.outputs if match(o)], "summary_case_prepared_target_changed"
        ).output_key
    else:
        target = None
    if target != prepared.target_output_key:
        raise ValueError("summary_case_prepared_target_changed")
    data = json.loads(prepared.task_data_json)
    raw = _safe(prepared.source)["task_evidence"]
    if any(
        canonical_json(data[key]) != canonical_json(raw[other])
        for key, other in (
            ("prompt", "prompt"),
            ("initial_state", "initial"),
            ("task_name", "task_name"),
        )
    ):
        raise ValueError("summary_case_prepared_task_data_changed")
    source_data = json.loads(prepared.source.source_json)["task"]["data"]
    expected_tools = source_data["zapier_tools"]
    if prepared.capture_mode != "retained_actual" and additional_tools:
        expected_tools = list(dict.fromkeys([*expected_tools, *additional_tools]))
    if canonical_json(data["zapier_tools"]) != canonical_json(expected_tools):
        raise ValueError("summary_case_prepared_task_tools_changed")
    return prepared


def validate_prepared_summary_case(prepared: PreparedSummaryCase) -> PreparedSummaryCase:
    return _validate_prepared_case(prepared, profile=_SUMMARY)
