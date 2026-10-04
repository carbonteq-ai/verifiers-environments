"""Typed report fields (``labeled_value``) and declared numeric precision.

Minimal reproductions (before these mechanisms):
- HR: block-scope ``mentions_together`` with ``excluding_values: ["$125"]``
  passed "Cost-per-applicant: $100 or $175" (only enumerated rivals fail) and
  ``sole`` rejected a legitimate "Spend: $12,000" in the same block;
- Finance: the excluded-row guard (source/derived amounts only) missed
  "Dispute Holdings — $1,000";
- Operations: an exact derived baseline (140000/3) could only be matched by a
  hand-rounded literal, so "46666.6666666667" and "46666.67" could not both be
  judged against the declared precision.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

TEXT = {"kind": "field", "path": ["effect", "body"], "domain": "string"}
REQUEST = {
    "Role": "Data Analyst",
    "Spend": "$12,000",
    "Applicants": "120",
    "Customer": "Dispute Holdings",
}


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


CPA = {
    "kind": "derived",
    "expression": {
        "kind": "decimal",
        "op": "div",
        "left": {"kind": "input", "format": "usd_string", "path": ["request", "Spend"]},
        "right": {"kind": "input", "format": "decimal_string", "path": ["request", "Applicants"]},
    },
}
HR = {
    "label": literal("Cost-per-applicant"),
    "entity": {"value": field("request", "Role"), "mode": "words"},
    "scope": "block",
    "value": CPA,
}
EXCLUDED = {"label": field("request", "Customer")}


def labeled(body, **spec):
    predicate = parse_predicate(
        {"op": "labeled_value", "text": TEXT, "format": "usd_string", **spec}
    )
    return evaluate_predicate(predicate, {"effect": {"body": body}, "request": REQUEST}).value


BLOCK = (
    "Data Analyst — Days Open: 50\nTotal Applicants: 120\nSpend: $12,000\nCost-per-applicant: {}"
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("$100", True),
        ("$100.00", True),
        ("100", True),
        (
            "$100 (Spend $12,000 / 120 applicants)",
            True,
        ),  # a later explanation is not a stated value
        ("$175", False),
        ("$100 or $175", False),
        ("$100 / $125", False),
        ("$100 (or $175)", False),
        ("$100-$175", False),
        ("$12,000 / 120 = $100", True),  # formula = result
        ("$12,000 / 120 = $100 or $175", False),
    ],
)
def test_hr_cost_per_applicant_hedges_fail_without_enumerating_rivals(value, expected):
    assert labeled(BLOCK.format(value), **HR) is expected


def test_hr_other_labels_and_other_entities_do_not_interfere():
    assert labeled("Data Analyst: Spend: $12,000; Cost per applicant: $100", **HR) is True
    assert (
        labeled(
            "Data Engineer\nCost-per-applicant: $90\n\nData Analyst\nCost-per-applicant: $100", **HR
        )
        is True
    )
    assert labeled("Data Analyst\nSpend: $12,000", **HR) is False  # never stated
    assert (
        labeled("Data Analyst\nCost-per-applicant: $100\nCost-per-applicant: $90", **HR) is False
    )  # conflict
    assert (
        labeled("Data Analyst cost per applicant for the quarter is $100", **HR) is None
    )  # outside representation
    assert labeled("Data Analyst\n> Cost-per-applicant: $100", **HR) is None  # quoted only
    assert (
        labeled(
            "Data Analyst\nTotal cost-per-applicant: $90\nCost-per-applicant: $100",
            **HR,
            excluding=["Total cost per applicant"],
        )
        is True
    )


@pytest.mark.parametrize(
    "body,expected",
    [
        ("Dispute Holdings — $1,000", True),
        ("Dispute Holdings — $0", True),
        ("$45,000 for Dispute Holdings", True),
        ("Dispute Holdings: $45,000 × 0 / 100 = $0", True),
        ("Dispute Holdings was excluded from the calculation.", False),
        ("Dispute Holdings: excluded (Do Not Include)", False),
        ("Dispute Holdings was excluded. Ending cash balance: $153,400", False),
        (
            "NovaTech Solutions — $40,000\nDispute Holdings was excluded from the calculation.",
            False,
        ),
        (
            "Dispute Holdings was excluded from the $153,400 ending balance",
            None,
        ),  # undecidable association
        ("> Dispute Holdings — $1,000", None),
    ],
)
def test_excluded_entity_entered_with_an_amount(body, expected):
    assert labeled(body, **EXCLUDED) is expected


def test_formula_lines_state_their_result_only():
    meridian = {"label": literal("Meridian Corp"), "value": literal("$15,000")}
    assert labeled("Meridian Corp: $30,000 × 50 / 100 = $15,000", **meridian) is True
    assert labeled("Meridian Corp: $30,000", **meridian) is False
    assert labeled("Meridian Corp: $30,000 × 50 / 100 =", **meridian) is None
    ending = {"label": literal("Ending cash balance"), "value": literal("$153,400")}
    assert (
        labeled("Ending cash balance: $200,000 + $70,000 − $116,600 = $153,400", **ending) is True
    )


def test_unavailable_inputs_stay_unknown_and_shapes_are_validated():
    assert labeled("Cost-per-applicant: $100", label=field("request", "Missing")) is None
    assert (
        labeled(
            "Data Analyst\nCost-per-applicant: $100",
            **{
                **HR,
                "value": {
                    "kind": "derived",
                    "expression": {
                        "kind": "input",
                        "format": "usd_string",
                        "path": ["request", "Nope"],
                    },
                },
            },
        )
        is None
    )
    with pytest.raises(ValidationError):
        parse_predicate(
            {
                "op": "labeled_value",
                "text": TEXT,
                "format": "usd_string",
                "label": literal("x"),
                "entity": {"value": literal("x"), "mode": "verbatim"},
            }
        )
    raw = parse_predicate(
        {"op": "labeled_value", "text": TEXT, "format": "usd_string", "label": literal("x")}
    )
    assert raw.model_dump(mode="json") == {
        "op": "labeled_value",
        "text": TEXT | {"allowed": []},
        "label": literal("x"),
        "scope": "line",
        "format": "usd_string",
    }


# Declared precision for exact derivations.

BASELINE = {
    "kind": "derived",
    "expression": {
        "kind": "decimal",
        "op": "div",
        "left": {"kind": "input", "format": "decimal_string", "literal": "140000"},
        "right": {"kind": "input", "format": "decimal_string", "literal": "3"},
    },
}


def mentions(text, value=BASELINE, **precision):
    raw = {
        "op": "mentions",
        "text": TEXT,
        "value": value,
        "mode": "amount",
        "format": "decimal_string",
    }
    if precision:
        raw["precision"] = precision
    return evaluate_predicate(parse_predicate(raw), {"effect": {"body": text}}).value


@pytest.mark.parametrize(
    "text,min2,min0,exactly2",
    [
        ("46666.67", True, True, True),
        ("46666.6666666667", True, True, False),
        ("46666.66", False, False, False),  # truncated, not rounded
        ("46666.670", False, False, False),  # wrong at its own (third) place
        ("46667", False, True, False),
        ("46666.7", False, True, False),
    ],
)
def test_declared_precision_accepts_only_correct_roundings(text, min2, min0, exactly2):
    assert mentions(f"Baseline {text} kWh") is None  # repeating quotient without declared precision
    assert mentions(f"Baseline {text} kWh", min_places=2) is min2
    assert mentions(f"Baseline {text} kWh", min_places=0) is min0
    assert mentions(f"Baseline {text} kWh", min_places=2, max_places=2) is exactly2


def test_precision_ties_exact_values_and_sole():
    half = {
        "kind": "derived",
        "expression": {
            "kind": "decimal",
            "op": "div",
            "left": {"kind": "input", "format": "decimal_string", "literal": "2125"},
            "right": {"kind": "input", "format": "decimal_string", "literal": "1000"},
        },
    }
    assert mentions("2.13", half, min_places=2, ties="half_up") is True
    assert mentions("2.12", half, min_places=2, ties="half_up") is False
    assert mentions("2.12", half, min_places=2, ties="half_even") is True
    assert mentions("2.125", half, min_places=3, max_places=3) is True  # exact
    assert (
        mentions("2.125", half, min_places=0, max_places=1) is True
    )  # exact beats the place bounds
    raw = {
        "op": "mentions",
        "text": TEXT,
        "value": BASELINE,
        "mode": "amount",
        "format": "decimal_string",
        "precision": {"min_places": 2},
        "sole": True,
    }
    assert (
        evaluate_predicate(
            parse_predicate(raw), {"effect": {"body": "46666.67 (46666.6666666667)"}}
        ).value
        is True
    )
    assert (
        evaluate_predicate(parse_predicate(raw), {"effect": {"body": "46666.67 or 46666.66"}}).value
        is False
    )


@pytest.mark.parametrize(
    "value",
    [
        literal("46666.67"),  # verbatim source text
        {
            "kind": "derived",
            "expression": {"kind": "input", "format": "decimal_string", "literal": "46666.67"},
        },
        {
            "kind": "derived",
            "expression": {
                "kind": "round",
                "scale": 2,
                "ties": "half_up",
                "value": BASELINE["expression"],
            },
        },
    ],
)
def test_precision_is_only_for_arithmetic_derivations(value):
    with pytest.raises(
        ValidationError, match="predicate_precision_requires_derived_arithmetic_amount"
    ):
        parse_predicate(
            {
                "op": "mentions",
                "text": TEXT,
                "value": value,
                "mode": "amount",
                "format": "decimal_string",
                "precision": {"min_places": 2},
            }
        )
    with pytest.raises(ValidationError):
        parse_predicate(
            {
                "op": "mentions",
                "text": TEXT,
                "value": BASELINE,
                "mode": "amount",
                "format": "decimal_string",
                "precision": {"min_places": 3, "max_places": 2},
            }
        )


def test_existing_mention_dumps_are_unchanged():
    raw = {
        "op": "mentions",
        "text": TEXT,
        "value": literal("$5"),
        "mode": "amount",
        "format": "usd_string",
    }
    assert "precision" not in parse_predicate(raw).model_dump(mode="json")


# Native simulator executions (genuine Gmail handler, validated native traces).

ROLES = [
    ("Data Analyst", "ana@example.com", "$12,000", "120"),
    ("Data Engineer", "eng@example.com", "$9,000", "60"),
]


def world():
    return {
        "google_sheets": {
            "spreadsheets": [{"id": "ss_rec", "title": "Recruiting"}],
            "worksheets": [
                {
                    "id": "ws_roles",
                    "spreadsheet_id": "ss_rec",
                    "title": "Roles",
                    "headers": ["Role", "Manager Email", "Spend", "Applicants"],
                }
            ],
            "rows": [
                {
                    "id": f"row_{index}",
                    "spreadsheet_id": "ss_rec",
                    "worksheet_id": "ws_roles",
                    "row_id": index + 2,
                    "cells": {
                        "Role": role,
                        "Manager Email": email,
                        "Spend": spend,
                        "Applicants": applicants,
                    },
                }
                for index, (role, email, spend, applicants) in enumerate(ROLES)
            ],
        },
        "gmail": {"messages": [], "drafts": []},
    }


def hr_contract():
    match = {
        "op": "all",
        "args": [
            {
                "op": "in",
                "left": field("request", "Manager Email"),
                "right": field("effect", "recipients", domain="sequence"),
            },
            {
                "op": "labeled_value",
                "text": field("effect", "body_text"),
                "format": "usd_string",
                "scope": "block",
                "label": literal("Cost-per-applicant"),
                "entity": {"value": field("request", "Role"), "mode": "words"},
                "value": CPA,
            },
        ],
    }
    return load_contract(
        canonical_json(
            {
                "schema_version": 1,
                "manifest_id": "labeled-values",
                "revision": "1",
                "public_request": "Email each hiring manager their role's cost-per-applicant.",
                "sources": {
                    "roles": {
                        "adapter": "google_sheets.rows@1",
                        "path": ["task_evidence", "initial", "google_sheets"],
                        "spreadsheet_id": "ss_rec",
                        "worksheet_id": "ws_roles",
                        "key_fields": ["Role"],
                    },
                    "sends": {"adapter": "gmail.messages@1", "kind": "send"},
                },
                "checks": [
                    {
                        "check_id": "cpa",
                        "signal_id": "hr.cpa",
                        "role": "goal",
                        "operator": "effects.required_when@1",
                        "semantics": "new_occurrence",
                        "population": "roles",
                        "source": "sends",
                        "required_when": {
                            "op": "eq",
                            "left": literal(True),
                            "right": literal(True),
                        },
                        "effect_match": match,
                        "match_cardinality": "per_candidate",
                    }
                ],
            }
        )
    )


def send(to, body):
    args = {"to": to, "subject": "Recruiting metrics", "body": body}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def native(monkeypatch, declared, calls, missing_ack=None):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(world(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    return sorted(
        (
            body["candidate_identity"][3] if body.get("candidate_identity") else None,
            body["status"],
            body["value"],
        )
        for batch in trace.assessment_batches
        for receipt in batch.run.execution_evidence
        if (body := json.loads(receipt.payload_json)).get("kind") == "finding"
        and body["status"] != "inapplicable"
    )


def report(role, spend, cpa):
    return f"{role}\nSpend: {spend}\nCost-per-applicant: {cpa}"


def test_native_hr_reports_correct_hedged_and_missing_ack(monkeypatch):
    declared = hr_contract()
    correct = [
        send("ana@example.com", report("Data Analyst", "$12,000", "$100")),
        send("eng@example.com", report("Data Engineer", "$9,000", "$150")),
    ]
    assert {item[1:] for item in native(monkeypatch, declared, correct)} == {("valid", 1)}
    hedged = [
        send("ana@example.com", report("Data Analyst", "$12,000", "$100 or $175")),
        correct[1],
    ]
    by_role = {item[0]: item[1:] for item in native(monkeypatch, declared, hedged)}
    assert sorted(by_role.values()) == [("valid", 0), ("valid", 1)] and len(by_role) == 2
    assert ("abstained", None) in {
        item[1:] for item in native(monkeypatch, declared, correct, missing_ack=0)
    }


# Real retained Luna episodes: native rescore and wire reload stay stable.


def replay(monkeypatch, path, sha, declared):
    if not path.exists():
        pytest.skip("retained Luna episode unavailable")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = cast(Any, episode.traces[0])
    data = AutomationBenchData.model_validate(trace.task.data.model_dump(mode="json"))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
        artifacts=dict(trace.state.artifacts),
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)

    def findings(item, start):
        return sorted(
            (
                body["check_id"],
                body.get("candidate_identity") and body["candidate_identity"][3],
                body["status"],
                body["value"],
            )
            for batch in item.assessment_batches[start:]
            for receipt in batch.run.execution_evidence
            if (body := json.loads(receipt.payload_json)).get("kind") == "finding"
        )

    asyncio.run(task.score(trace))
    first = findings(trace, 0)
    assert not trace.assessment_errors and not trace.credit_errors
    start = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    assert findings(trace, start) == first
    loaded = cast(Any, vf.WireEpisode.model_validate_json(episode.model_dump_json()).traces[0])
    loaded.state = trace.state
    start = len(loaded.assessment_batches)
    asyncio.run(task.score(loaded))
    assert findings(loaded, start) == first
    assert trace.rewards == scalar and loaded.rewards == scalar and path.read_bytes() == raw
    return first


CASHFLOW = Path(
    "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/"
    "remaining700/timed/4a92941f9a4711ccee33b0ab7ec21f39655a2676c3e79cd96bc6fb92e58b38d1/episode.json"
)
CASHFLOW_SHA = "b3de71d5ae7fd73429fc8f838ccf4ae883bfb13ec03836106330e7eb3ab6f3f8"


def test_recorded_cash_flow_inflows_and_excluded_entity(monkeypatch):
    expected = {
        "kind": "derived",
        "expression": {
            "kind": "decimal",
            "op": "div",
            "left": {
                "kind": "decimal",
                "op": "mul",
                "left": {"kind": "input", "format": "usd_string", "path": ["request", "Amount"]},
                "right": {
                    "kind": "input",
                    "format": "decimal_string",
                    "path": ["request", "Collection Probability"],
                },
            },
            "right": {"kind": "input", "format": "decimal_string", "literal": "100"},
        },
    }
    body = field("effect", "body_text")
    population = {
        "adapter": "google_sheets.rows@1",
        "path": ["task_evidence", "initial", "google_sheets"],
        "spreadsheet_id": "ss_cashflow",
        "worksheet_id": "ws_ar_due",
        "key_fields": ["Customer"],
    }
    status = {"op": "eq", "left": field("request", "Status"), "right": literal("Include")}
    declared = load_contract(
        canonical_json(
            {
                "schema_version": 1,
                "manifest_id": "cashflow-labeled",
                "revision": "1",
                "public_request": "Forecast",
                "sources": {
                    "ar": population,
                    "sends": {"adapter": "gmail.messages@1", "kind": "send"},
                },
                "checks": [
                    {
                        "check_id": "inflow",
                        "signal_id": "finance.inflow",
                        "role": "goal",
                        "operator": "effects.required_when@1",
                        "semantics": "new_occurrence",
                        "population": "ar",
                        "source": "sends",
                        "required_when": status,
                        "match_cardinality": "per_candidate",
                        "effect_match": {
                            "op": "labeled_value",
                            "text": body,
                            "format": "usd_string",
                            "label": field("request", "Customer"),
                            "value": expected,
                        },
                    },
                    {
                        "check_id": "excluded-entered",
                        "signal_id": "finance.excluded_entered",
                        "role": "harm",
                        "operator": "effects.prohibited_when@1",
                        "population": "ar",
                        "source": "sends",
                        "prohibited_when": {"op": "not", "arg": status},
                        "match_cardinality": "per_candidate",
                        "effect_match": {
                            "op": "labeled_value",
                            "text": body,
                            "format": "usd_string",
                            "label": field("request", "Customer"),
                        },
                    },
                ],
            }
        )
    )
    first = replay(monkeypatch, CASHFLOW, CASHFLOW_SHA, declared)
    inflows = {
        item[1]: item[2:] for item in first if item[0] == "inflow" and item[2] != "inapplicable"
    }
    assert set(inflows.values()) == {("valid", 1)} and len(inflows) == 3
    excluded = {item[2:] for item in first if item[0] == "excluded-entered"}
    assert ("valid", 1) not in excluded and ("valid", 0) in excluded


ENERGY = Path(
    "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/"
    "remaining700/untimed/8655364429afd3a155dc69761809d235fd60fa5299615030e5fe708636724b44/episode.json"
)
ENERGY_SHA = "418cf12cb4c6c7bba777d05d117be913e8aadb86df9c7f3cac6415ab58748df1"


def test_recorded_energy_baseline_with_declared_precision(monkeypatch):
    months = [
        {"kind": "input", "format": "decimal_string", "path": ["request", name]}
        for name in ("Nov 2025 (kWh)", "Dec 2025 (kWh)", "Jan 2026 (kWh)")
    ]
    average = {
        "kind": "derived",
        "expression": {
            "kind": "decimal",
            "op": "div",
            "left": {
                "kind": "decimal",
                "op": "add",
                "left": {"kind": "decimal", "op": "add", "left": months[0], "right": months[1]},
                "right": months[2],
            },
            "right": {"kind": "input", "format": "decimal_string", "literal": "3"},
        },
    }

    def contract(precision):
        value = {
            "op": "labeled_value",
            "text": field("effect", "body_text"),
            "format": "decimal_string",
            "label": literal("expected baseline"),
            "entity": {"value": field("request", "Building"), "mode": "words"},
            "value": average,
        }
        if precision:
            value["precision"] = precision
        return load_contract(
            canonical_json(
                {
                    "schema_version": 1,
                    "manifest_id": "energy-precision",
                    "revision": "1",
                    "public_request": "Report",
                    "sources": {
                        "usage": {
                            "adapter": "google_sheets.rows@1",
                            "path": ["task_evidence", "initial", "google_sheets"],
                            "spreadsheet_id": "ss_energy",
                            "worksheet_id": "ws_monthly",
                            "key_fields": ["Building"],
                        },
                        "sends": {"adapter": "gmail.messages@1", "kind": "send"},
                    },
                    "checks": [
                        {
                            "check_id": "baseline",
                            "signal_id": "ops.baseline",
                            "role": "goal",
                            "operator": "effects.required_when@1",
                            "semantics": "new_occurrence",
                            "population": "usage",
                            "source": "sends",
                            "match_cardinality": "per_candidate",
                            "required_when": {
                                "op": "eq",
                                "left": field("request", "Building"),
                                "right": literal("HQ Tower"),
                            },
                            "effect_match": value,
                        }
                    ],
                }
            )
        )

    sheet = (
        json.loads(ENERGY.read_bytes())["traces"][0]["task"]["data"]["initial_state"][
            "google_sheets"
        ]
        if ENERGY.exists()
        else None
    )
    if sheet is not None and not any(
        item.get("id") == "ss_energy" for item in sheet["spreadsheets"]
    ):
        pytest.skip("energy spreadsheet identity differs")
    precise = {
        item[2:]
        for item in replay(monkeypatch, ENERGY, ENERGY_SHA, contract({"min_places": 2}))
        if item[2] != "inapplicable"
    }
    assert precise == {("valid", 1)}
    undeclared = {
        item[2:]
        for item in replay(monkeypatch, ENERGY, ENERGY_SHA, contract(None))
        if item[2] != "inapplicable"
    }
    assert undeclared == {("abstained", None)}  # repeating quotient: precision must be declared
