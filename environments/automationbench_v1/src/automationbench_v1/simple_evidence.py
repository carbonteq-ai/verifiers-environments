"""Four reviewed direct requests, checked from acknowledged simulator effects.

These predicates assess requested state, not the model's reasoning, response
quality or every possible guard. Asana's maintained simulator uses action records
as its creation abstraction; that is not proof of an external Asana object.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime

from .capture import canonical_json
from .effect_evidence import world_transitions
from .effect_index import EffectIndex
from .hr_rules import Finding

SUPPORTED = frozenset(
    {
        "simple.sf_case_priority_high",
        "simple.hs_update_contact_phone",
        "simple.asana_api_docs_task",
        "simple.gcal_one_on_one",
    }
)

REQUESTS = {
    "simple.sf_case_priority_high": "Update Salesforce case 500002 priority to 'High'.",
    "simple.hs_update_contact_phone": "Update the phone number for HubSpot contact hs_006 (Emma Chen) to +1-555-5050.",
    "simple.asana_api_docs_task": "Please create an Asana task named 'Update API documentation'. Add it to the Engineering project (proj_eng) in workspace ws_prod, and set the due date to March 7, 2026.",
    "simple.gcal_one_on_one": "Create a calendar event called '1:1 with Jordan' on Thursday, February 26, 2026 at 11:00 AM EST (16:00 UTC) for 30 minutes on the work calendar (ID: cal_primary). Add jordan.lee@company.example.com as an attendee.",
}


def _service(world: Mapping, service: str) -> Mapping:
    value = world.get(service, {})
    if not isinstance(value, Mapping):
        raise ValueError("service_state_schema_unresolved")  # noqa: TRY004
    return value


def _records(world: Mapping, service: str, collection: str) -> Sequence[Mapping]:
    records = _service(world, service).get(collection, [])
    if not isinstance(records, (list, tuple)) or any(
        not isinstance(item, Mapping) for item in records
    ):
        raise ValueError("record_collection_schema_unresolved")
    ids = [item.get("id") for item in records]
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("record_identity_unresolved")
    return records


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("event_timezone_unresolved")
    return instant


def _declared_fields_match(declared, hydrated) -> bool:
    """Check supplied facts; do not invent values for omitted schema defaults.

    Collection membership and declared list order are retained. This projection
    establishes the declared initial facts, not every omitted initial field.
    """
    if isinstance(declared, dict):
        return isinstance(hydrated, Mapping) and all(
            key in hydrated and _declared_fields_match(value, hydrated[key])
            for key, value in declared.items()
        )
    if isinstance(declared, list):
        return (
            isinstance(hydrated, (list, tuple))
            and len(declared) == len(hydrated)
            and all(
                _declared_fields_match(left, right)
                for left, right in zip(declared, hydrated, strict=True)
            )
        )
    return type(declared) is type(hydrated) and declared == hydrated


def _matches(world: Mapping, task: str) -> tuple[str, ...]:
    if task == "simple.sf_case_priority_high":
        return tuple(
            item["id"]
            for item in _records(world, "salesforce", "cases")
            if item["id"] == "500002" and item.get("priority") == "High"
        )
    if task == "simple.hs_update_contact_phone":
        return tuple(
            item["id"]
            for item in _records(world, "hubspot", "contacts")
            if item["id"] == "hs_006" and item.get("phone") == "+1-555-5050"
        )
    if task == "simple.asana_api_docs_task":
        actions = _service(world, "asana").get("actions", {})
        if not isinstance(actions, Mapping):
            raise ValueError("action_container_schema_unresolved")
        records = actions.get("create_task", [])
        if not isinstance(records, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in records
        ):
            raise ValueError("creation_records_schema_unresolved")
        if any(not isinstance(item.get("params", {}), Mapping) for item in records):
            raise ValueError("creation_parameters_schema_unresolved")
        ids = [item.get("id") for item in records]
        if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("creation_identity_unresolved")
        expected = {
            "name": "Update API documentation",
            "workspace": "ws_prod",
            "project": "proj_eng",
            "dueDate": "2026-03-07",
        }
        return tuple(
            item["id"]
            for item in records
            if all(item.get("params", {}).get(key) == value for key, value in expected.items())
        )
    if task == "simple.gcal_one_on_one":
        matched = []
        for event in _records(world, "google_calendar", "events"):
            if (
                event.get("calendarid") != "cal_primary"
                or event.get("summary") != "1:1 with Jordan"
            ):
                continue
            attendees = event.get("attendees", [])
            if not isinstance(attendees, (list, tuple)) or any(
                not isinstance(item, str) for item in attendees
            ):
                raise ValueError("attendee_schema_unresolved")
            if (
                "jordan.lee@company.example.com" in attendees
                and _instant(event["start__dateTime"]) == _instant("2026-02-26T16:00:00Z")
                and _instant(event["end__dateTime"]) == _instant("2026-02-26T16:30:00Z")
            ):
                matched.append(event["id"])
        return tuple(matched)
    raise ValueError("unsupported_direct_request")


def evaluate_simple(source: dict) -> tuple[Finding, ...]:
    evidence = source["task_evidence"]
    task = evidence["task_name"]
    prompt = " ".join(
        item.get("content", "") for item in evidence["prompt"] if item.get("role") == "user"
    )
    if task not in REQUESTS or prompt != REQUESTS[task]:
        raise ValueError("public_request_revision_unresolved")
    initial_matches = set(_matches(evidence["initial"], task))
    final_matches = set(_matches(evidence["final"], task))
    creation = task in {"simple.asana_api_docs_task", "simple.gcal_one_on_one"}
    if creation:
        final_matches -= initial_matches
    transitions = world_transitions(source)
    index = EffectIndex(transitions)
    chain = index.serial_chain()
    ordered = chain.ordered if chain.status == "qualified" else transitions
    complete = evidence.get("complete") is True
    coverage = (
        complete
        and chain.status == "qualified"
        and ordered[0].expected_revision == 0
        and ordered[0].before_json is not None
        and _declared_fields_match(
            {key: value for key, value in evidence["initial"].items() if key != "meta"},
            index.world(ordered[0].before_json),
        )
        and ordered[-1].after_json == canonical_json(evidence["final"])
    )
    recipient = None
    for transition in ordered:
        if creation and recipient is not None:
            continue
        if (
            transition.evidence_status != "acknowledged"
            or transition.action is None
            or transition.action.status != "returned"
            or transition.before_json is None
            or transition.after_json is None
        ):
            continue
        before = set(_matches(index.world(transition.before_json), task))
        after = set(_matches(index.world(transition.after_json), task))
        if (after - before) & final_matches:
            recipient = transition.invocation_id
    already_correct = bool(initial_matches & final_matches) and not creation
    if complete and final_matches and (recipient is not None or already_correct):
        goal = Finding(
            "simple.requested_state",
            1.0,
            "already_correct_state" if already_correct else "verified_requested_effect",
            None if already_correct or not coverage else recipient,
        )
    elif coverage:
        goal = Finding("simple.requested_state", 0.0, "requested_effect_not_completed")
    else:
        goal = Finding("simple.requested_state", None, "completion_evidence_unresolved")
    return (
        goal,
        Finding(
            "simple.recording_coverage",
            1.0 if coverage else None,
            "reconciled_retained_world" if coverage else "recording_or_finalization_unresolved",
        ),
    )
