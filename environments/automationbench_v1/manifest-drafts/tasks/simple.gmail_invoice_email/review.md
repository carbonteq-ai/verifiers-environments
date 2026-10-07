# simple.gmail_invoice_email (round 6)

Status: **qualified_candidate** — 6/6 in-scope obligations expressed, 0 gaps, 3 out of scope.

## Obligations

- O1-email-to-rachel (goal, expressed, `invoice-email-sent`): Send with the address in 'to'.
- O2-subject (goal, expressed, `invoice-subject`): Subject equals the quoted text exactly.
- O3-amount (report, expressed, `invoice-amount`): Body states $12,500 as the only money amount (sole: true blocks hedges and ranges).
- O4-period-and-service (report, expressed, `invoice-period-and-service`): 'February' and 'consulting' in the same body paragraph.
- O5-payment-terms (report, expressed, `invoice-payment-terms`): Body mentions 'Net 30' as words.
- O6-file-reference (report, expressed, `invoice-file-reference`): Body contains the filename verbatim.
- O7-says-attached (report, out_of_scope): Phrasing of the attachment notice is wording.
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: invoice-amount=0.0, invoice-email-sent=0.0, invoice-file-reference=0.0, invoice-payment-terms=0.0, invoice-period-and-service=0.0, invoice-subject=0.0.

## Simulator runs and gaming

H1 '$12,500 / $1,250' and H7 '$12,500 to $12,750' -> O3 0; C2 '$12,500.00' paraphrase -> 1; H6 another address -> all 0.
