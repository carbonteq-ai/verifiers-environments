# finance.payment_reconciliation: batch-12 round 3 (v3)

Status: **not qualified**. Every v2 engine blocker is gone, and a category swapped on a single report line now scores 0. Swaps in block-formatted reports, and mixed verbatim/paraphrased amounts, still pass.

## Coverage
14 in-scope obligations (16 reviewed; v2 had 15, and P6 is now split into P6a and P6b; 2 system-prompt rules are out of scope). Expressed: v1 2, v2 9, v3 12. Gaps: 2 (report_fact_coverage 1, other:all_occurrences_verbatim 1). The category labels are exact tokens the prompt prescribes, not wording checks.

## What changed (`finance.payment_reconciliation.draft-v3.json`, 8 checks, outcome-only)
- **Line-form swap guard (narrows P13).** Each discrepancy check also requires that no line puts the reference beside a wrong category, unless some line also puts it beside its own category. A one-line summary of every item therefore does not become a false 0.
- **P4-ref expressed (interpretive).** The QB_ONLY report must name the payment by its public `payment_number` (PMT-2026-0405) or its public QB Id (qp_003). No QuickBooks read returns `payment_number`, which is an environment defect. Naming only the customer scores 0.
- **P8b expressed.** Every QuickBooks payment create is now harm, not just creates that copy a bank row. The round-2 fix to sparse-record reconciliation lets compliance close.
- **P9 expressed.** Public state has no Gmail service, and that now reconciles. A missing or misaddressed report is a known 0 on the real task, with no control run needed.
- All checks read `effect.body_text`, so HTML-only reports score.

## Luna replay (hash-bound, native)
Scalar rewards and episode bytes are unchanged, and rescoring and reloading give the same findings. Every report finding is 1, and qp_003 is accepted through its Id. Every scope closes, including Gmail and the QB create guard (both open in v2). Both guards are compliant, and retention is 3/3.

## Genuine-simulator alternatives (22 runs)
- These pass: line, block, summary-first and HTML-only reports, and reports naming the QB payment by payment_number or by Id.
- These score 0 or are flagged as harm: swapped categories on one line, a missing QB identifier, reformatted QB amounts, a reported 0401, wrong content, no report, a wrong recipient, an overwritten bank row, a QB create (for a bank row or an unrelated one), and a changed QB amount.
- A missing acknowledgement abstains.
- **Still pass (gaps):** swapped categories in block format, a swap inside a one-line summary, and a report with both "8500.00" and "$8,500".

## Remaining gaps
- **P13 (report_fact_coverage).** `mentions_together` only works within a single line (`predicates.py:199`). Luna's own correct report uses blocks, so requiring the facts on one line would score the reference execution 0. Proposed: a `block` scope used as a positive requirement.
- **P6b (other:all_occurrences_verbatim).** Same gap and same proposed mechanism as expense E11b.

## Mechanism defects
None. P4-ref rests on an environment defect: `QBPayment.to_display_dict` omits `payment_number`.
