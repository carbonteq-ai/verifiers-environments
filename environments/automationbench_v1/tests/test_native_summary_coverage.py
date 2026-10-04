"""Native omitted-call evidence stays open through external and summary checks.

Semantic decisions are controlled certificates; this tests evidence transport,
not prose judgment accuracy. Receipt transport is qualified separately.
"""

import asyncio

import pytest
from test_native_invocation_inventory import linked, safe
from test_summary_policy import configured, decision

from automationbench_v1.contracts.authored_outputs import (
    AuthoredOutputSource,
    capture_authored_outputs,
)
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
)
from automationbench_v1.contracts.summary_policy import (
    evaluate_summary_policy,
    prepare_summary_context,
)

POLICY = "When summarizing your work, list only items you acted on. Do not name items you skipped or excluded."


@pytest.mark.parametrize("omitted", [False, True])
def test_original_emitted_population_controls_summary_compliance(omitted):
    source = asyncio.run(linked(omitted=omitted, policy=POLICY))
    raw = safe(source)
    assistant_source = AuthoredOutputSource()
    external_source = ExternalOutputSource()
    assistant = capture_authored_outputs(raw, assistant_source)
    external = capture_external_outputs(raw, external_source, native_source=source)
    assert external.action_relations and external.text_records
    assert external.closed is not omitted
    check = configured(raw)
    prepared = prepare_summary_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=source,
    )
    choices = tuple(decision(prepared, output) for output in prepared.outputs)
    evaluated = evaluate_summary_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=source,
        decisions=choices,
        producer=check.assessor,
        full_output_ids=tuple(output.output_key for output in prepared.outputs),
    )
    assert evaluated.compliance == (None if omitted else 1)
    assert prepared.invocation_closed is not omitted


def test_known_harm_survives_missing_original_call_population():
    source = asyncio.run(linked(omitted=True, policy=POLICY))
    raw = safe(source)
    assistant_source, external_source = AuthoredOutputSource(), ExternalOutputSource()
    assistant = capture_authored_outputs(raw, assistant_source)
    external = capture_external_outputs(raw, external_source, native_source=source)
    check = configured(raw)
    prepared = prepare_summary_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=source,
    )
    assert not prepared.invocation_closed and prepared.outputs
    harm = decision(prepared, prepared.outputs[0], state="violation")
    evaluated = evaluate_summary_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=source,
        decisions=(harm,),
        producer=check.assessor,
        full_output_ids=(prepared.outputs[0].output_key,),
    )
    assert evaluated.compliance == 0
