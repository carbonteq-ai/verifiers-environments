"""Round-7 engine corrections: each test reproduces one shared defect."""

import json

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.hubspot.crm import hubspot_update_contact
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population
from automationbench_v1.contracts.retained_records import (
    RetainedRecordCheck,
    RetainedRecordSource,
    capture_record_retention,
    evaluate_retained_records,
)

# --- Item 1: HubSpot lifecycle_stage under its schema alias -------------------


def _hubspot_public():
    # Public initial state is raw JSON written with the schema alias.
    return {"hubspot": {
        "contacts": [
            {"id": "H1", "email": "a@example.com", "lifecycle_stage": "customer", "properties": {"churn_risk": "low"}},
            {"id": "H2", "email": "b@example.com", "lifecycle_stage": "lead"},
            {"id": "H3", "email": "c@example.com"},
        ],
        "companies": [
            {"id": "C1", "name": "Acme", "lifecycle_stage": "customer"},
            {"id": "C2", "name": "Beta", "lifecyclestage": "opportunity"},
        ],
    }}


def _with_public_initial(source, public):
    source["task_evidence"]["initial"] = json.loads(json.dumps(public))
    return source


@pytest.mark.parametrize("collection,key", [("contacts", "email"), ("companies", "name")])
@pytest.mark.parametrize("stage_path", [["lifecycle_stage"], ["lifecyclestage"]])
def test_initial_records_read_lifecycle_stage_by_name_or_alias(collection, key, stage_path):
    spec = InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "hubspot", collection],
        "fields": {"Stage": stage_path, "Key": [key]}, "key_fields": ["Key"]})
    source = _with_public_initial(run_operations(_hubspot_public(), []), _hubspot_public())
    stages = [json.loads(row.cells_json).get("Stage") for row in capture_population(source, spec).rows]
    expected = {"contacts": ["customer", "lead", None], "companies": ["customer", "opportunity"]}[collection]
    # A record that omits the field stays unread (unknown), never the schema default.
    assert stages == expected


def test_alias_and_name_that_disagree_are_unread():
    public = _hubspot_public()
    public["hubspot"]["contacts"][0]["lifecyclestage"] = "lead"
    spec = InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "hubspot", "contacts"],
        "fields": {"Stage": ["lifecycle_stage"], "Key": ["email"]}, "key_fields": ["Key"]})
    source = _with_public_initial(run_operations(_hubspot_public(), []), public)
    assert "Stage" not in json.loads(capture_population(source, spec).rows[0].cells_json)


def test_unknown_alias_is_still_rejected():
    with pytest.raises(ValueError, match="population_field_path_unsupported"):
        InitialCollectionSource.model_validate({
            "path": ["task_evidence", "initial", "hubspot", "contacts"],
            "fields": {"Stage": ["lifecycle"], "Key": ["email"]}, "key_fields": ["Key"]})


# --- Item 2: final.records@1 reads one key of a mapping field ---------------


def _set_risk(contact_id, value):
    args = {"contact_id": contact_id, "properties": {"churn_risk": value}}
    return zapier("hubspot_update_contact", args, lambda world: hubspot_update_contact(world, **args))


@pytest.mark.parametrize("calls,expected", [([], 0.0), ([_set_risk("H1", "high")], 1.0),
                                            ([_set_risk("H1", "high"), _set_risk("H1", "medium")], 0.0)])
def test_final_records_read_a_key_inside_a_mapping_field(calls, expected):
    population = InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "hubspot", "contacts"],
        "fields": {"Stage": ["lifecycle_stage"], "Email": ["email"]}, "key_fields": ["Email"]})
    terminal = RetainedRecordSource.model_validate({
        "path": ["task_evidence", "final", "hubspot", "contacts"],
        "fields": {"Risk": ["properties", "churn_risk"], "Props": ["properties"]}})
    check = RetainedRecordCheck.model_validate({
        "check_id": "churn-risk", "signal_id": "contact.churn_risk", "role": "goal",
        "population": "contacts", "source": "terminal",
        "required_when": {"op": "eq", "left": {"kind": "field", "path": ["request", "Stage"]},
                          "right": {"kind": "literal", "value": "customer"}},
        "retained_when": {"op": "all", "args": [
            {"op": "eq", "left": {"kind": "field", "path": ["retained", "Risk"]},
             "right": {"kind": "literal", "value": "high"}},
            {"op": "eq", "left": {"kind": "field", "path": ["retained", "Props", "churn_risk"]},
             "right": {"kind": "literal", "value": "high"}}]}})
    source = _with_public_initial(run_operations(_hubspot_public(), calls), _hubspot_public())
    retention = capture_record_retention(source, terminal)
    assert retention.closed
    result = evaluate_retained_records(source, check, {"contacts": capture_population(source, population)},
        retention, population_sources={"contacts": population}, retention_source=terminal)
    by_id = {finding.native_record_id: finding for finding in result.findings}
    assert by_id["H1"].status == "valid" and by_id["H1"].value == expected
    assert by_id["H2"].status == "inapplicable"
    assert by_id["H3"].status == "abstained"  # stage omitted from public data: unknown, not "lead"


# --- Item 3: Gmail filing writes are not unknown sends ----------------------


def _gmail_initial():
    return {"gmail": {"messages": [
        {"id": "m1", "thread_id": "t1", "from_": "client@example.com", "to": ["me@example.com"],
         "subject": "Workspace", "body_plain": "Please confirm", "label_ids": ["INBOX", "UNREAD"]},
    ], "drafts": []}}


def _gmail(tool, handler, **args):
    return zapier(tool, args, lambda world: handler(world, **args))


def _filing_calls():
    from automationbench.tools.zapier.gmail.actions import (
        gmail_archive_email,
        gmail_mark_as_read,
        gmail_star_messages,
        gmail_trash_email,
    )
    from automationbench.tools.zapier.gmail.label import (
        gmail_add_label_to_email,
        gmail_create_label,
        gmail_remove_label_from_email,
        gmail_remove_thread_label,
    )
    return [
        _gmail("gmail_create_label", gmail_create_label, name="Project X"),
        _gmail("gmail_add_label_to_email", gmail_add_label_to_email, message_id="m1", new_label_ids="Project X"),
        _gmail("gmail_remove_label_from_email", gmail_remove_label_from_email, message_id="m1", label_ids="UNREAD"),
        _gmail("gmail_remove_thread_label", gmail_remove_thread_label, thread_id="t1", label_ids="Project X"),
        _gmail("gmail_mark_as_read", gmail_mark_as_read, message_id="m1"),
        _gmail("gmail_star_messages", gmail_star_messages, message_ids="m1"),
        _gmail("gmail_archive_email", gmail_archive_email, message_id="m1"),
        _gmail("gmail_trash_email", gmail_trash_email, message_id="m1"),
    ]


def test_gmail_filing_writes_close_send_scope_with_no_send():
    from automationbench_v1.contracts.notification_effects import (
        NotificationEffectSource,
        capture_notification_effects,
    )

    evidence = capture_notification_effects(run_operations(_gmail_initial(), _filing_calls()), NotificationEffectSource())
    assert evidence.complete and evidence.effects == ()


def test_gmail_filing_then_send_keeps_the_send_and_a_content_change_stays_unknown():
    from automationbench.tools.zapier.gmail.message import gmail_send_email
    from automationbench_v1.contracts.notification_effects import (
        NotificationEffectSource,
        capture_notification_effects,
    )

    send = _gmail("gmail_send_email", gmail_send_email, to="client@example.com", subject="Confirmed", body="Done")
    evidence = capture_notification_effects(
        run_operations(_gmail_initial(), [*_filing_calls()[:2], send]), NotificationEffectSource())
    assert evidence.complete and [fact.kind for fact in evidence.effects] == ["send"]

    # A filing handler name whose observed change touches message content is
    # not a filing write: the send inventory stays incomplete.
    def rewrite(world):
        world.gmail.messages[0].label_ids.append("Project X")
        world.gmail.messages[0].body_plain = "Changed"
        return json.dumps({"success": True})

    tampered = run_operations(_gmail_initial(), [zapier("gmail_add_label_to_email", {"message_id": "m1"}, rewrite)])
    assert not capture_notification_effects(tampered, NotificationEffectSource()).complete


# --- Item 4: quantifiers over list items -------------------------------------


def _member_where(email="x@example.com", role="viewer"):
    return {"op": "all", "args": [
        {"op": "eq", "left": {"kind": "field", "path": ["item", "email"], "domain": "string"},
         "right": {"kind": "literal", "value": email}},
        {"op": "eq", "left": {"kind": "field", "path": ["item", "role"], "domain": "string"},
         "right": {"kind": "literal", "value": role}}]}


def _quantified(op, where, path=("effect", "record", "members")):
    from automationbench_v1.contracts.predicates import parse_predicate

    return parse_predicate({"op": op, "items": {"kind": "field", "path": list(path)}, "where": where})


@pytest.mark.parametrize("members,any_value,all_value", [
    ([], False, True),
    ([{"email": "x@example.com", "role": "viewer"}], True, True),
    ([{"email": "y@example.com", "role": "viewer"}, {"email": "x@example.com", "role": "viewer"}], True, False),
    ([{"email": "x@example.com", "role": "editor"}], False, False),
    ([{"email": "x@example.com"}], None, None),  # undecidable item (role unread)
    ([{"email": "x@example.com"}, {"email": "x@example.com", "role": "viewer"}], True, None),
    ([{"email": "x@example.com"}, {"email": "y@example.com", "role": "viewer"}], None, False),
])
def test_item_quantifiers_are_three_valued(members, any_value, all_value):
    from automationbench_v1.contracts.predicates import evaluate_predicate

    context = {"effect": {"record": {"members": members}}}
    assert evaluate_predicate(_quantified("any_item", _member_where()), context).value is any_value
    assert evaluate_predicate(_quantified("all_items", _member_where()), context).value is all_value


@pytest.mark.parametrize("context", [{}, {"effect": {"record": {"members": None}}},
                                     {"effect": {"record": {"members": "x@example.com"}}}])
def test_unreadable_item_lists_stay_unknown(context):
    from automationbench_v1.contracts.predicates import evaluate_predicate

    for op in ("any_item", "all_items"):
        assert evaluate_predicate(_quantified(op, _member_where()), context).value is None


def test_scalar_items_and_nested_quantifiers():
    from automationbench_v1.contracts.predicates import evaluate_predicate

    has_label = _quantified("any_item", {"op": "eq", "left": {"kind": "field", "path": ["item"]},
                                         "right": {"kind": "literal", "value": "Project X"}},
                            path=("effect", "label_names"))
    assert evaluate_predicate(has_label, {"effect": {"label_names": ["INBOX", "Project X"]}}).value is True
    assert evaluate_predicate(has_label, {"effect": {"label_names": ["INBOX"]}}).value is False
    rooms = _quantified("any_item", {"op": "any_item", "items": {"kind": "field", "path": ["item", "members"]},
                                     "where": _member_where()}, path=("effect", "rooms"))
    result = evaluate_predicate(rooms, {"effect": {"rooms": [{"members": []}, {"members": [
        {"email": "x@example.com", "role": "viewer"}]}]}})
    assert result.value is True
    assert ("effect", "rooms", 1, "members", 0, "role") in result.evidence_paths


def test_item_references_are_validated_in_contracts():
    from automationbench_v1.contracts.predicates import context_paths

    raw = {"op": "any_item", "items": {"kind": "field", "path": ["effect", "members"]}, "where": _member_where()}
    assert list(context_paths(raw)) == [("effect", "members")]
    raw_outside = _member_where()
    assert ("item", "email") in list(context_paths(raw_outside))  # rejected by check roots
    with pytest.raises(ValueError):
        _quantified("any_item", _member_where(), path=("item",))
    from automationbench_v1.contracts.predicates import parse_predicate
    with pytest.raises(ValueError):
        parse_predicate({"op": "all_items", "items": {"kind": "field", "path": ["effect", "m"], "domain": "sequence"},
                         "where": _member_where()})


def test_item_quantifier_in_an_obligation_loads_and_outside_item_is_rejected():
    from test_manifest_effect_joins import contract

    raw = contract().model_dump(mode="json")
    effect_match = raw["checks"][0]["effect_match"]
    effect_match["args"].append({"op": "any_item", "items": {"kind": "field", "path": ["effect", "record", "params"]},
                                 "where": {"op": "present", "value": {"kind": "field", "path": ["item"]}}})
    load_contract(canonical_json(raw))
    effect_match["args"].append({"op": "present", "value": {"kind": "field", "path": ["item", "email"]}})
    with pytest.raises(ValueError):
        load_contract(canonical_json(raw))


# --- Item 5: join timing "after" -------------------------------------------


def test_after_timing_sees_only_strictly_later_effects(monkeypatch):
    from test_manifest_effect_joins import contract, create, outcome

    from automationbench.tools.zapier.monday.actions import monday_change_status_column_value

    def early(w):
        return monday_change_status_column_value(w, board_id="brd_training", item_id="monday_x",
                                                 column_id="status", value_label="Scheduled")
    board_only = {"op": "eq", "left": {"kind": "field", "path": ["joined", "record", "params", "board_id"],
                                       "domain": "string"},
                  "right": {"kind": "field", "path": ["request", "Board"], "domain": "string"}}
    raw = contract(where=board_only).model_dump(mode="json")
    raw["checks"][0]["effect_joins"][0]["timing"] = "after"
    declared = load_contract(canonical_json(raw))
    status_first = [("monday_change_status_column_value", {"item_id": "x"}, early), create()]
    assert outcome(monkeypatch, status_first, declared) == ("valid", 1)
    assert outcome(monkeypatch, [create(), status_first[0]], declared) == ("valid", 0)
    assert outcome(monkeypatch, [create(), status_first[0], create()], declared) == ("valid", 1)


# --- Item 7: LinkedIn read evidence -----------------------------------------


def _linkedin_initial():
    return {"linkedin": {
        "profiles": [
            {"id": "urn:li:person:me", "first_name": "Sam", "last_name": "Seller", "email": "sam@example.com"},
            {"id": "urn:li:person:ana", "first_name": "Ana", "last_name": "Lopez", "email": "ana@acme.example",
             "headline": "VP Ops at Acme", "public_profile_url": "https://linkedin.com/in/ana"},
        ],
        # Public connections carry no id: hydration generates one.
        "connections": [{"owner_id": "urn:li:person:me", "connected_profile_id": "urn:li:person:bo",
                         "first_name": "Bo", "last_name": "Chen", "email": "bo@beta.example", "company": "Beta"},
                        {"owner_id": "urn:li:person:me", "first_name": "Cy", "last_name": "Anon"}],
        "companies": [{"id": "1001", "name": "Acme", "admin_ids": ["urn:li:person:me"]}],
        "posts": [{"id": "7001", "author_id": "urn:li:person:ana", "text": "Hiring ops leads in Austin"}],
        "current_user_id": "urn:li:person:me",
    }}


def _linkedin_call(tool, **args):
    from automationbench.tools.zapier.linkedin import companies, posts, profiles

    handler = next(getattr(module, tool) for module in (profiles, posts, companies) if hasattr(module, tool))
    return zapier(tool, args, lambda world: handler(world, **args))


def _linkedin_material(calls, world=None):
    from test_manifest_guard_assessments import native_fixture

    public = world or _linkedin_initial()
    source = run_operations(public, calls)
    _, _, trace = native_fixture(source)
    source["tool_execution_events"] = [{"source": "tool_server", "receipt_json": event.receipt_json}
                                       for event in trace.tool_execution_events]
    source["state_write_receipts"] = [receipt.model_dump(mode="json") for receipt in trace.state_write_receipts]
    source["task_evidence"]["initial"] = json.loads(json.dumps(public))
    return source


def _linkedin_facts(source):
    from automationbench_v1.contracts.linkedin_reads import (
        LinkedInReadSource,
        capture_linkedin_reads,
    )

    evidence = capture_linkedin_reads(source, LinkedInReadSource())
    return evidence, [json.loads(fact.params_json) for fact in evidence.effects if fact.status == "qualified"]


@pytest.mark.parametrize("call,expected", [
    (("linkedin_get_profile", {"profile_id": "urn:li:person:ana"}), [("profile", "urn:li:person:ana")]),
    (("linkedin_find_profile", {"keywords": "ana"}), [("profile", "urn:li:person:ana")]),
    (("linkedin_find_profile", {"company": "Beta"}), [("connection", "urn:li:person:bo")]),
    (("linkedin_get_profile", {"profile_id": "urn:li:person:bo"}), [("connection", "urn:li:person:bo")]),
    (("linkedin_get_connections", {}), [("connection", "urn:li:person:bo"), ("connection", None)]),
    (("linkedin_get_my_profile", {}), [("profile", "urn:li:person:me")]),
    (("linkedin_find_post", {"author_id": "urn:li:person:ana"}), [("post", "7001")]),
    (("linkedin_find_post", {"post_id": "7001"}), [("post", "7001")]),
    (("linkedin_get_company", {"company_id": "1001"}), [("company", "1001")]),
    (("linkedin_list_companies", {"name": "acme"}), [("company", "1001")]),
])
def test_linkedin_reads_return_stored_records_with_stable_identities(call, expected):
    evidence, facts = _linkedin_facts(_linkedin_material([_linkedin_call(call[0], **call[1])]))
    assert evidence.complete, evidence.reason
    assert [(fact["record_type"], fact["identity"]) for fact in facts] == expected
    for fact in facts:
        if fact["identity"] == "urn:li:person:ana":
            assert fact["email"] == "ana@acme.example" and fact["full_name"] == "Ana Lopez"
            assert fact["public_profile_url"] == "https://linkedin.com/in/ana"
        if fact["identity"] == "urn:li:person:bo":
            assert fact["email"] == "bo@beta.example" and fact["profile_id"] == "urn:li:person:bo"


@pytest.mark.parametrize("call", [("linkedin_get_profile", {"profile_id": "urn:li:person:nobody"}),
                                  ("linkedin_find_profile", {"keywords": "zzz"}),
                                  ("linkedin_find_post", {"post_id": "404"})])
def test_failed_and_empty_linkedin_reads_return_nothing(call):
    evidence, facts = _linkedin_facts(_linkedin_material([_linkedin_call(call[0], **call[1])]))
    assert evidence.complete and facts == []


def test_linkedin_writes_are_not_reads_and_rewritten_results_cannot_invent_reads():
    import copy

    from automationbench.tools.zapier.linkedin.posts import linkedin_create_share

    share = zapier("linkedin_create_share", {"comment": "Hello"},
                   lambda world: linkedin_create_share(world, comment="Hello"))
    evidence, facts = _linkedin_facts(_linkedin_material([share]))
    assert evidence.complete and facts == []
    source = _linkedin_material([_linkedin_call("linkedin_get_profile", profile_id="urn:li:person:ana")])
    tampered = copy.deepcopy(source)
    for event in tampered["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt["phase"] != "returned":
            continue
        capture = json.loads(receipt["evidence_json"][0])
        result = json.loads(json.loads(capture["action"]["result_json"]))
        result["profile"]["headline"] = "CEO at Acme"
        capture["action"]["result_json"] = json.dumps(json.dumps(result))
        receipt["evidence_json"] = [json.dumps(capture)]
        receipt["result_json"] = capture["action"]["result_json"]
        event["receipt_json"] = json.dumps(receipt)
    evidence, facts = _linkedin_facts(tampered)
    assert not evidence.complete and facts == []


def test_linkedin_read_joins_an_outreach_obligation(monkeypatch):
    import asyncio

    from test_manifest_guard_assessments import native_fixture

    from automationbench.tools.zapier.gmail.message import gmail_send_email
    from automationbench_v1 import manifest_assessments

    contract = load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "linkedin-read-fixture", "revision": "1",
        "public_request": "Check each attendee's LinkedIn profile before emailing them.",
        "sources": {
            "attendees": {"adapter": "initial.records@1", "path": ["task_evidence", "initial", "linkedin", "profiles"],
                          "fields": {"Email": ["email"]}, "key_fields": ["Email"]},
            "reads": {"adapter": "linkedin.reads@1"},
            "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
        "checks": [{
            "check_id": "email-after-profile-read", "signal_id": "sales.researched_outreach", "role": "goal",
            "operator": "effects.required_when@1", "semantics": "new_occurrence", "population": "attendees",
            "source": "sends", "match_cardinality": "per_candidate",
            "required_when": {"op": "eq", "left": {"kind": "field", "path": ["request", "Email"]},
                              "right": {"kind": "literal", "value": "ana@acme.example"}},
            "effect_joins": [{"alias": "profile", "source": "reads", "timing": "before", "match": "any",
                              "where": {"op": "eq", "left": {"kind": "field", "path": ["joined", "identity"]},
                                        "right": {"kind": "field", "path": ["candidate", "native_record_id"]}}}],
            "effect_match": {"op": "all", "args": [
                {"op": "eq", "left": {"kind": "field", "path": ["join", "profile"]},
                 "right": {"kind": "literal", "value": "matched"}},
                {"op": "in", "left": {"kind": "field", "path": ["request", "Email"]},
                 "right": {"kind": "field", "path": ["effect", "to"], "domain": "sequence"}}]}}]}))
    send = zapier("gmail_send_email", {"to": "ana@acme.example", "subject": "Hi", "body": "Saw your post"},
                  lambda world: gmail_send_email(world, to="ana@acme.example", subject="Hi", body="Saw your post"))
    read = _linkedin_call("linkedin_get_profile", profile_id="urn:li:person:ana")
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)

    def outcome(calls):
        task, _, trace = native_fixture(run_operations(_linkedin_initial(), calls))
        asyncio.run(task.score(trace))
        assert not trace.assessment_errors and not trace.credit_errors
        values = {}
        for batch in trace.assessment_batches:
            for receipt in batch.run.execution_evidence:
                body = json.loads(receipt.payload_json)
                if body.get("kind") == "finding" and body["candidate_identity"][-1] == "urn:li:person:ana":
                    values = (body["status"], body["value"])
        return values

    assert outcome([read, send]) == ("valid", 1)
    assert outcome([send, read]) == ("valid", 0)


# --- Item 8: hyphen-terminated reference prefixes ---------------------------


@pytest.mark.parametrize("mode,text,expected", [
    ("verbatim", "Logged as INS-2026-014 today", False),  # verbatim keeps token boundaries
    ("prefix", "Logged as INS-2026-014 today", True),
    ("prefix", "Logged as INS- (pending)", False),
    ("prefix", "Logged as XINS-2026-014", False),
    ("prefix", "> quoted INS-2026-014", None),
    ("verbatim", "Logged as INS-", True),
])
def test_prefix_mentions_match_reference_codes_without_loosening_verbatim(mode, text, expected):
    from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate

    predicate = parse_predicate({"op": "mentions", "text": {"kind": "field", "path": ["effect", "body"], "domain": "string"},
                                 "value": {"kind": "literal", "value": "INS-"}, "mode": mode})
    assert evaluate_predicate(predicate, {"effect": {"body": text}}).value is expected


# --- Item 9: update facts expose newly appended list items ------------------


def test_record_update_facts_expose_added_list_items():
    from automationbench.tools.zapier.gmail.label import gmail_add_label_to_email
    from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate
    from automationbench_v1.contracts.record_writes import RecordWriteSource, capture_record_writes

    label = _gmail("gmail_add_label_to_email", gmail_add_label_to_email, message_id="m1",
                   new_label_ids="Project X", mark_as_read=True)
    source = run_operations(_gmail_initial(), [label])
    evidence = capture_record_writes(source, RecordWriteSource(service="gmail", collection=("messages",), kind="update"))
    assert evidence.complete
    params = json.loads(evidence.effects[0].params_json)
    assert params["added_items"]["label_ids"] == ["Project X"]
    assert params["added_items"]["to"] == [] and "subject" not in params["added_items"]
    new_label = parse_predicate({"op": "any_item", "items": {"kind": "field", "path": ["effect", "added_items", "label_ids"]},
                                 "where": {"op": "eq", "left": {"kind": "field", "path": ["item"]},
                                           "right": {"kind": "literal", "value": "Project X"}}})
    assert evaluate_predicate(new_label, {"effect": params}).value is True
    # A label that was already there is not an added item.
    params["added_items"]["label_ids"] = []
    assert evaluate_predicate(new_label, {"effect": params}).value is False


def test_added_items_is_a_multiset_difference():
    from automationbench_v1.contracts.record_writes import _added_items

    before = {"tags": ["a", "b", "a"], "notes": [{"v": 1}], "name": "x"}
    after = {"tags": ["a", "b", "a", "a", "c"], "notes": [{"v": 2}], "name": "y", "new": ["z"]}
    assert _added_items(before, after) == {"tags": ["a", "c"], "notes": [{"v": 2}]}


# --- Item 10: shared decode and capture caches keep receipts identical -------


def test_capture_memo_returns_what_a_fresh_capture_returns():
    from dataclasses import asdict

    from automationbench.tools.zapier.gmail.message import gmail_send_email
    from automationbench_v1 import manifest_guard_assessments as guards
    from automationbench_v1.contracts.notification_effects import NotificationEffectSource

    send = _gmail("gmail_send_email", gmail_send_email, to="client@example.com", subject="Confirmed", body="Done")
    source = run_operations(_gmail_initial(), [send])
    spec = NotificationEffectSource()
    first = guards.capture_effect_input(source, spec)
    assert guards.capture_effect_input(json.loads(json.dumps(source)), spec) is first  # same content: shared
    fresh = guards._capture_effect_input(source, spec)
    assert asdict(first) == asdict(fresh)
    # Changed content is a different key, never a stale hit.
    source["state_write_receipts"] = []
    changed = guards.capture_effect_input(source, spec)
    assert changed is not first and not changed.complete and first.complete


def test_decoded_snapshots_are_shared_and_immutable():
    from automationbench_v1.effect_evidence import persisted_transitions
    from automationbench_v1.effect_index import EffectIndex

    source = run_operations(_gmail_initial(), _filing_calls()[:2])
    first, second = EffectIndex(persisted_transitions(source)), EffectIndex(persisted_transitions(source))
    occurrence = first.occurrences[0]
    assert first.world(occurrence.after_json) is second.world(occurrence.after_json)
    with pytest.raises(TypeError):
        first.world(occurrence.after_json)["gmail"]["messages"] = ()  # type: ignore[index]
