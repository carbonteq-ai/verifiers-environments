# finance.expense_split_allocation: batch-12 round 3 (v3)

Status: **not qualified**. Each charge amount must now sit on the same line as its expense, which removes the false passes v2 gave on Luna. Two obligations are still gaps.

## Coverage
16 in-scope obligations (19 reviewed; 3 out of scope as system-prompt or rounding items, excluded from the totals). Expressed: v1 8, v2 12, v3 14. Gaps: 2 (other:all_occurrences_verbatim 1, other:agent_defined_log_schema 1). The checks match exact facts only (expense and department names, amounts, recipients); none are wording checks.

## What changed (`finance.expense_split_allocation.draft-v3.json`, 19 checks, outcome-only)
- **E18 closed with `mentions_together`.** The six `*-charge-emailed` checks now need the expense name and the department's share on one readable line. Both cent and whole-dollar rounding still count.
- **HTML-only emails score.** Every check reads `effect.body_text`, so an HTML-only email is now read as text. In v2 these abstained (D4).
- **E13 reclassified as expressed. No new mechanism was added.** Each expense × department outcome already has a per-expense check, and every input to it is bound to a public source by digest. What v2 called missing was generality, a single check that would work on any data. The brief puts task parameters in manifest data, so this does not leave a public outcome unchecked.
- The round-2 verbatim fix now rejects "$36,000.00" for "$36,000": the verbatim check gives 0 and the paraphrase guard flags it.

## Luna replay (hash-bound, native)
Scalar rewards and episode bytes are unchanged, and rescoring and reloading give the same findings. Every scope closes. Holiday party passes. Every wrong share, in both the log and the emails, is a known 0, including the three training findings that falsely passed in v2.

## Genuine-simulator alternatives (16 runs)
- These pass: cent rounding, whole-dollar rounding, one email to all heads, a markdown table, a square-footage header line, and HTML-only emails.
- These score 0 on the affected checks: stale headcount, shares swapped between expenses, wrong shares, "$36,000.00", and "36000 USD". The paraphrase guard flags the last two.
- A missing acknowledgement abstains and never becomes a false 0.
- **Limitation:** a correct email in block format, with the expense on one line and "Your share: $X" on the next, scores 0 on the charge checks.
- **Gap:** a message that uses both "$36,000" and "36000 USD" passes everything (E11b).

## Remaining gaps
- **E11b (other:all_occurrences_verbatim).** No mention mode tests the written form of every occurrence. Proposed: a `non_verbatim_amount` mode, true when some number equals the value but is written differently. It would also serve payment P6b and deferred DR12b.
- **E12 (other:agent_defined_log_schema).** Logs whose amount column has a different header abstain. I probed `service.record_writes@1` with `values_text`, which ignores column names, on Luna. It falsely passes the training rows, because each row's Sq Ft cell (3,000, 2,000, 1,000) equals the correct share. Proposed: a `usd_marked` amount format, or a labelled Sheets text view that can exclude non-amount columns.

## Mechanism defects
None in mechanisms 6–8.
