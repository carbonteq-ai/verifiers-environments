"""Read reported SDK thread usage without inventing model-call token counts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SdkResponseAccounting(BaseModel):
    """Pinned SDK completed-response reporting, not physical provider accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: Literal["codex-0.160-completed-response-usage-v1"] = (
        "codex-0.160-completed-response-usage-v1"
    )
    status: Literal["reconciled", "unavailable"]
    reason: str | None = None
    response_ids: tuple[str, ...] = ()
    reported_counts: dict[str, int | None] = Field(default_factory=dict)
    first_response_input: int | None = None
    maximum_response_input: int | None = None
    cumulative_response_input: int | None = None
    reasoning_inclusion: Literal["reported_output_detail", "unqualified"] = "unqualified"


class SdkBudgetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    thread_id: str
    output_budget: int
    status: Literal["observed", "unavailable"]
    reason: str | None = None
    reported_counts: dict[str, int | None] = Field(default_factory=dict)
    observed_updates: int = 0
    output_remaining: int | None = None
    threshold_reached: bool | None = None
    overshoot_tokens: int | None = None
    observed_output_lower_bound: int | None = None
    observed_overshoot_lower_bound: int | None = None
    enforcement: Literal["observed_threshold"] = "observed_threshold"
    reasoning_inclusion: Literal["unqualified"] = "unqualified"
    response_accounting: SdkResponseAccounting | None = None


_COUNTS = (
    "inputTokens",
    "cachedInputTokens",
    "cacheWriteInputTokens",
    "outputTokens",
    "reasoningOutputTokens",
    "totalTokens",
)


def reconcile_sdk_responses(
    events: Iterable[dict],
    *,
    thread_id: str,
    fresh_thread: bool,
    sdk_version: str | None,
    raw_response_events_requested: bool,
) -> SdkResponseAccounting:
    """Reconcile every observed completed response against terminal totals.

    SDK 0.160 emits raw completion before updating cumulative usage, including
    completions with absent usage. This detects omitted reported completions;
    it does not cover abandoned streams or unreported provider-internal work.
    Input counts measure reported response inputs, not exact context windows.
    """

    def unavailable(reason: str) -> SdkResponseAccounting:
        return SdkResponseAccounting(status="unavailable", reason=reason)

    if not fresh_thread or sdk_version != "0.160.0" or raw_response_events_requested is not True:
        return unavailable("pinned_fresh_raw_response_contract_unavailable")
    responses: dict[str, dict] = {}
    terminal = None
    last_total = None
    last_total_index = last_response_index = -1
    cumulative_turn_ids = []
    cumulative_snapshots = []
    required = tuple(key for key in _COUNTS if key != "cacheWriteInputTokens")
    for index, event in enumerate(events):
        method = event.get("method")
        if method not in (
            "rawResponse/completed",
            "thread/tokenUsage/updated",
            "turn/completed",
            "error",
        ):
            continue
        params = event.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id:
            return unavailable("response_thread_identity_mismatch")
        if method == "error":
            # A recovered request can have generated partial output without a
            # completed-response receipt. Its usage cannot be inferred from the
            # successful retry or final cumulative reported counts.
            return unavailable("failed_or_retried_request_usage_unavailable")
        if terminal is not None:
            return unavailable("accounting_event_after_terminal")
        if method == "turn/completed":
            terminal = params.get("turn")
            if (
                not isinstance(terminal, dict)
                or terminal.get("status") != "completed"
                or not isinstance(terminal.get("id"), str)
                or not terminal["id"]
            ):
                return unavailable("successful_terminal_unavailable")
        elif method == "thread/tokenUsage/updated":
            usage = params.get("tokenUsage")
            last_total = usage.get("total") if isinstance(usage, dict) else None
            cumulative_snapshots.append(last_total)
            cumulative_turn_ids.append(params.get("turnId"))
            last_total_index = index
        else:
            response_id = params.get("responseId")
            if not isinstance(response_id, str) or not response_id:
                return unavailable("response_identity_unavailable")
            if response_id in responses:
                if json.dumps(responses[response_id], sort_keys=True) != json.dumps(
                    params, sort_keys=True
                ):
                    return unavailable("conflicting_duplicate_response")
                continue
            responses[response_id] = params
            last_response_index = index
    if terminal is None or not responses or not isinstance(last_total, dict):
        return unavailable("terminal_response_usage_unavailable")
    if last_total_index <= last_response_index:
        return unavailable("final_cumulative_update_unavailable")
    if any(turn_id != terminal.get("id") for turn_id in cumulative_turn_ids):
        return unavailable("cumulative_turn_identity_mismatch")
    previous_snapshot = dict.fromkeys(required, 0)
    for snapshot in cumulative_snapshots:
        if not isinstance(snapshot, dict) or any(
            type(snapshot.get(key)) is not int or snapshot[key] < previous_snapshot[key]
            for key in required
        ):
            return unavailable("cumulative_usage_missing_invalid_or_regressed")
        previous_snapshot = {key: snapshot[key] for key in required}
    totals: dict[str, int | None] = dict.fromkeys(_COUNTS, 0)
    inputs = []
    for params in responses.values():
        if params.get("turnId") != terminal.get("id"):
            return unavailable("response_turn_identity_mismatch")
        usage = params.get("usage")
        if not isinstance(usage, dict):
            return unavailable("completed_response_usage_missing")
        if any(type(usage.get(key)) is not int or usage[key] < 0 for key in required):
            return unavailable("completed_response_usage_invalid")
        if (
            usage["cachedInputTokens"] > usage["inputTokens"]
            or (usage["reasoningOutputTokens"] > usage["outputTokens"])
            or usage["totalTokens"] != usage["inputTokens"] + usage["outputTokens"]
        ):
            return unavailable("completed_response_usage_inconsistent")
        inputs.append(usage["inputTokens"])
        for key in _COUNTS:
            value = usage.get(key)
            if key == "cacheWriteInputTokens" and value is None:
                totals[key] = None
            elif type(value) is not int or value < 0:
                return unavailable("completed_response_usage_invalid")
            else:
                previous = totals[key]
                if previous is not None:
                    totals[key] = previous + value
    if any(
        type(last_total.get(key)) is not int or last_total[key] != totals[key] for key in required
    ):
        return unavailable("terminal_cumulative_usage_mismatch")
    if totals["cacheWriteInputTokens"] is not None and (
        type(last_total.get("cacheWriteInputTokens")) is not int
        or last_total["cacheWriteInputTokens"] != totals["cacheWriteInputTokens"]
    ):
        return unavailable("terminal_cache_write_usage_mismatch")
    return SdkResponseAccounting(
        status="reconciled",
        response_ids=tuple(responses),
        reported_counts=totals,
        first_response_input=inputs[0],
        maximum_response_input=max(inputs),
        cumulative_response_input=sum(inputs),
        reasoning_inclusion="reported_output_detail",
    )


def summarize_sdk_usage(
    events: Iterable[dict],
    *,
    thread_id: str,
    fresh_thread: bool,
    output_budget: int = 16_384,
) -> SdkBudgetSummary:
    """Summarize one fresh thread's cumulative ``tokenUsage.total`` snapshots.

    ``turnId`` changes do not reset accounting. No per-request or peak-context
    counts can be recovered from these totals. A resumed/pre-existing thread
    needs a separately retained baseline and is deliberately unsupported here.
    Raw events remain in the native trace; this result is a derived summary.
    Missing values stay unknown. Counter regressions require reconciliation.
    """
    if not thread_id or type(fresh_thread) is not bool:
        raise ValueError("thread identity and explicit freshness are required")
    if type(output_budget) is not int or output_budget <= 0:
        raise ValueError("output budget must be a positive integer")
    if not fresh_thread:
        return SdkBudgetSummary(
            thread_id=thread_id,
            output_budget=output_budget,
            status="unavailable",
            reason="existing_thread_requires_retained_baseline",
        )
    latest: dict[str, int | None] = {}
    known: dict[str, int] = {}
    updates = 0
    for event in events:
        if event.get("method") != "thread/tokenUsage/updated":
            continue
        params = event.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id:
            raise ValueError("usage event differs from retained thread identity")
        usage = params.get("tokenUsage")
        total = usage.get("total") if isinstance(usage, dict) else None
        if not isinstance(total, dict):
            raise TypeError("usage event lacks cumulative total")
        snapshot = {}
        for key in _COUNTS:
            value = total.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("reported token counts must be nonnegative integers")
            if value is not None:
                if value < known.get(key, 0):
                    raise ValueError("cumulative counter regressed; reconcile before dispatch")
                known[key] = value
            snapshot[key] = value
        if (
            snapshot["cachedInputTokens"] is not None
            and snapshot["inputTokens"] is not None
            and snapshot["cachedInputTokens"] > snapshot["inputTokens"]
        ):
            raise ValueError("cached input exceeds reported input")
        latest = snapshot
        updates += 1
    output = latest.get("outputTokens")
    lower_bound = known.get("outputTokens")
    return SdkBudgetSummary(
        thread_id=thread_id,
        output_budget=output_budget,
        status="observed" if output is not None else "unavailable",
        reason=None if output is not None else "no_reported_output_total",
        reported_counts=latest,
        observed_updates=updates,
        output_remaining=None if output is None else max(0, output_budget - output),
        threshold_reached=(
            True
            if lower_bound is not None and lower_bound >= output_budget
            else None
            if output is None
            else False
        ),
        overshoot_tokens=None if output is None else max(0, output - output_budget),
        observed_output_lower_bound=lower_bound,
        observed_overshoot_lower_bound=(
            None if lower_bound is None else max(0, lower_bound - output_budget)
        ),
    )


def output_budget_eligibility(
    summary: SdkBudgetSummary,
    *,
    final_usage_confirmed: bool,
    reasoning_inclusion_confirmed: bool,
    required_budget: int = 16_384,
) -> tuple[Literal["within_budget", "over_budget", "unverified"], str]:
    """Budget clause only; task eligibility also requires outcome and guard proof.

    Confirmation flags must come from qualified producer/terminal evidence, not
    the absence of an error. Larger-budget rescue attempts do not establish a
    solution under the original budget, even if their eventual output is small.
    For the pinned SDK route, derive both flags only from a reconciled native
    ``response_accounting`` contract; this verifies reported completed-response
    counters, not physical provider-internal generation.
    """
    if type(required_budget) is not int or required_budget <= 0:
        raise ValueError("eligibility budget must be a positive integer")
    if type(final_usage_confirmed) is not bool or type(reasoning_inclusion_confirmed) is not bool:
        raise TypeError("usage confirmation must be explicit booleans")
    if summary.output_budget != required_budget:
        return "unverified", "different_attempt_budget"
    if summary.observed_output_lower_bound is not None and (
        summary.observed_output_lower_bound > required_budget
    ):
        return "over_budget", "observed_output_exceeds_budget"
    if not final_usage_confirmed or not reasoning_inclusion_confirmed:
        return "unverified", "usage_contract_or_finalization_unqualified"
    output = summary.reported_counts.get("outputTokens")
    if summary.status != "observed" or output is None:
        return "unverified", "final_output_unavailable"
    return (
        ("within_budget", "final_output_within_budget")
        if output <= required_budget
        else ("over_budget", "final_output_exceeds_budget")
    )


def retain_sdk_budget(info: dict, output_budget: int) -> None:
    """Attach derived accounting to native info without discarding invalid evidence."""
    sdk = info.get("codex_sdk")
    if not isinstance(sdk, dict):
        return
    records = sdk.get("events", [])
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        info["automationbench_output_budget"] = {
            "status": "invalid",
            "reason": "invalid_sdk_journal",
        }
        return
    starts = [record for record in records if record.get("kind") == "thread_started"]
    if len(starts) != 1 or sdk.get("fresh_thread_requested") is not True:
        info["automationbench_output_budget"] = {
            "status": "unavailable",
            "reason": "fresh_thread_binding_unavailable",
            "output_budget": output_budget,
        }
        return
    try:
        thread_id = starts[0]["response"]["thread"]["id"]
        events = [record["event"] for record in records if record.get("kind") == "event"]
        if any(not isinstance(event, dict) for event in events):
            raise TypeError("SDK event payload must be an object")
        summary = summarize_sdk_usage(
            events,
            thread_id=thread_id,
            fresh_thread=True,
            output_budget=output_budget,
        )
        accounting = reconcile_sdk_responses(
            events,
            thread_id=thread_id,
            fresh_thread=True,
            sdk_version=sdk.get("sdk_version"),
            raw_response_events_requested=starts[0].get("raw_response_events_requested") is True,
        )
        summary = summary.model_copy(update={"response_accounting": accounting})
        info["automationbench_output_budget"] = summary.model_dump(mode="json")
    except (KeyError, TypeError, ValueError) as error:
        # Retention must succeed even when usage is unusable; it cannot authorize
        # subsequent dispatch, and the original SDK events remain in place.
        info["automationbench_output_budget"] = {
            "status": "invalid",
            "reason": str(error),
            "output_budget": output_budget,
        }
