"""Static handler footprints and the scope closures that depend on them."""

import copy

import pytest
from pydantic import ValidationError
from test_manifest_notification_effects import send
from test_notification_evidence import run_operations, zapier

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.google_sheets.row import google_sheets_append_row
from automationbench.tools.zapier.slack.users import slack_find_user_by_name
from automationbench_v1.contracts import handler_scope
from automationbench_v1.contracts.handler_scope import (
    cannot_touch,
    handler_footprints,
    outside_service,
)
from automationbench_v1.contracts.service_hydration import public_service_matches
from automationbench_v1.contracts.sheet_effects import SheetEffectSource, capture_sheet_effects
from automationbench_v1.contracts.slack_effects import SlackEffectSource, capture_slack_effects


def test_every_installed_handler_resolves_to_world_fields():
    footprints = handler_footprints()
    unknown = sorted(name for name, footprint in footprints.items() if footprint is None)
    # A new unresolved handler must be reviewed, never silently trusted.
    assert unknown == []
    fields = set(WorldState.model_fields)
    assert all(footprint <= fields for footprint in footprints.values() if footprint is not None)


@pytest.mark.parametrize("name,expected", [
    ("gmail_send_email", {"gmail"}),
    ("gmail_find_email", {"gmail"}),
    ("google_sheets_update_row", {"google_sheets"}),  # helper imported in the body
    ("google_drive_find_multiple_files", {"google_drive", "google_sheets"}),
    ("bamboohr_updated_employee_poll", {"bamboohr"}),
    ("search_tools", set()),
])
def test_known_handler_footprints(name, expected):
    assert handler_footprints()[name] == frozenset(expected)


@pytest.mark.parametrize("name", ["api_fetch", "custom_tool", "", None, 3])
def test_unregistered_or_malformed_names_are_unknown(name):
    assert not cannot_touch(name, "gmail")


def helper_outside(world):
    return world


def dynamic(world, service="gmail"):
    return getattr(world, service)


def aliased(world):
    other = world
    return other.gmail


def method_call(world):
    return world.model_dump()


def escapes(world):
    return helper_outside(world)


def direct(world):
    return world.gmail.messages, world.slack


@pytest.mark.parametrize("func,expected", [
    (dynamic, None), (aliased, None), (method_call, None), (escapes, None),
    (direct, frozenset({"gmail", "slack"})),
])
def test_unresolvable_world_use_is_unknown(func, expected):
    assert handler_scope._footprint(func, frozenset({"world"}), handler_scope._fields(), {}) == expected


def test_closure_requires_both_footprint_and_unchanged_service():
    before = {"gmail": {"messages": []}, "airtable": {"records": []}}
    changed = {"gmail": {"messages": [{"id": "m"}]}, "airtable": {"records": []}}
    assert outside_service("airtable_create_record", "gmail", before, before)
    assert not outside_service("airtable_create_record", "gmail", before, changed)
    assert not outside_service("gmail_send_email", "gmail", before, before)
    assert not outside_service("api_fetch", "gmail", before, before)


def world():
    return {"slack": {"channels": [{"id": "C1", "name": "general"}],
                      "users": [{"id": "U1", "name": "Sarah Jones", "email": "sarah@example.com"}],
                      "messages": []},
            "google_sheets": {"worksheets": [{"id": "w", "spreadsheet_id": "s", "title": "W"}], "rows": []},
            "zoho_desk": {"tickets": []}}


def append():
    args = {"spreadsheet": "s", "worksheet": "w", "row": {"Item": "A"}}
    return zapier("google_sheets_append_row", args, lambda w: google_sheets_append_row(w, **args))


def zoho_ticket():
    return zapier("zoho_desk_create_ticket", {"subject": "PR"}, lambda w: {"success": True})


def test_alternative_service_keeps_sheet_scope_open():
    plain = SheetEffectSource(kind="append", spreadsheet_id="s", worksheet_id="w")
    declared = plain.model_copy(update={"alternative_services": ("zoho_desk",)})
    assert "alternative_services" not in plain.model_dump(mode="json")
    data = run_operations(world(), [zoho_ticket(), append()])
    assert capture_sheet_effects(data, plain).complete
    evidence = capture_sheet_effects(data, SheetEffectSource.model_validate(declared.model_dump()))
    assert not evidence.complete and evidence.reason == "sheet_alternative_channel_unobserved"
    assert any(fact.status == "qualified" for fact in evidence.effects)


@pytest.mark.parametrize("services", [("google_sheets",), ("zoho_desk", "zoho_desk"), ("not_a_service",)])
def test_alternative_services_must_be_distinct_other_world_services(services):
    with pytest.raises(ValidationError, match="sheet_alternative_services_invalid"):
        SheetEffectSource(kind="append", spreadsheet_id="s", worksheet_id="w", alternative_services=services)


def test_slack_read_and_unrelated_calls_close_send_scope_and_sparse_initial_reconciles():
    args = {"full_name": "Sarah Jones"}
    read = zapier("slack_find_user_by_name", args, lambda w: slack_find_user_by_name(w, **args))
    data = run_operations(world(), [read, append()])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = world()
    assert sparse["task_evidence"]["initial"] != data["task_evidence"]["initial"]
    evidence = capture_slack_effects(sparse, SlackEffectSource(kind="channel_message"))
    assert evidence.complete, evidence.reason
    assert evidence.effects == ()


def test_slack_without_calls_reconciles_sparse_initial_with_final():
    data = run_operations(world(), [])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = world()
    assert capture_slack_effects(sparse, SlackEffectSource(kind="channel_message")).complete
    altered = copy.deepcopy(sparse)
    altered["task_evidence"]["initial"]["slack"]["users"][0]["name"] = "Someone Else"
    assert not capture_slack_effects(altered, SlackEffectSource(kind="channel_message")).complete


def test_public_service_matching_rejects_dropped_keys():
    initial = {"gmail": {"messages": [], "emails": [{"id": "x"}], "drafts": []}}
    hydrated = WorldState.model_validate({"gmail": initial["gmail"]}).model_dump(mode="json")["gmail"]
    assert not public_service_matches(initial, "gmail", hydrated)
    assert public_service_matches({"gmail": {"messages": [], "drafts": []}}, "gmail",
                                  WorldState.model_validate({}).model_dump(mode="json")["gmail"])


def test_gmail_send_beside_unrelated_service_is_complete():
    from automationbench_v1.contracts.notification_effects import (
        NotificationEffectSource,
        capture_notification_effects,
    )

    data = run_operations({**world(), "gmail": {"messages": [], "drafts": []}}, [zoho_ticket(), send()])
    assert capture_notification_effects(data, NotificationEffectSource()).complete


def test_gmail_absent_from_public_state_and_zero_calls_close():
    from automationbench_v1.contracts.notification_effects import (
        NotificationEffectSource,
        capture_notification_effects,
    )

    data = run_operations(world(), [append()])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = world()  # no gmail at all
    assert capture_notification_effects(sparse, NotificationEffectSource()).complete
    empty = run_operations(world(), [])
    empty["task_evidence"]["initial"] = world()
    assert capture_notification_effects(empty, NotificationEffectSource()).complete


def test_gmail_reads_close_over_unrelated_calls():
    from test_manifest_gmail_observations import evidence, initial, material, positive, read

    seeded = {**world(), **initial()}
    observed = evidence(material([append(), read("find")], seeded))
    assert observed.complete, observed.reason
    assert positive(observed)


def test_html_only_send_exposes_readable_body_text():
    import json

    from automationbench_v1.contracts.notification_effects import (
        NotificationEffectSource,
        capture_notification_effects,
    )

    html = "<p>Total amortization: $4,900</p><ul><li>Insurance</li><li>Hosting</li></ul><script>x</script>"
    data = run_operations({**world(), "gmail": {"messages": [], "drafts": []}},
                          [send(body=html, body_type="html")])
    (fact,) = capture_notification_effects(data, NotificationEffectSource()).effects
    assert fact.params_json is not None
    params = json.loads(fact.params_json)
    assert params["body_plain"] is None
    assert params["body_text"].splitlines() == ["Total amortization: $4,900", "Insurance", "Hosting"]
