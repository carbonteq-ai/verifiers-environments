# finance.invoice_reconciliation (round 6)

Draft: 3 report obligations and 1 guard over Slack #finance-alerts posts. 7 / 7 in-scope obligations expressed, 0 gaps, 3 out of scope (system-prompt rules, report wording).

- AR-only (INV-3003) and accounting-only (INV-3005) invoices: invoice number beside its verbatim amount on one line or blank-line block, no second money value in that unit (`sole`).
- Amount mismatch (INV-3007, AR $6,300.00 vs accounting $4,800.00): invoice and both verbatim amounts together. Under Dispute is not excluded.
- Guard: naming an excluded or reconciled invoice (INV-3006 credit applied; INV-3001 name-only; INV-3004; INV-3002 whose corrected $8,750.00 entry matches AR) is harm.
- Missing/present is derived with `exists` over both exports; the accounting export is keyed [Invoice #, Amount] because INV-3002 appears twice.

Luna never read the data or posted; all checks abstain. Simulator: correct line, block and per-message reports score 1 with a clean guard; excluded/stale-duplicate/name-only alerts are penalised; rounded or hedged items earn nothing; missing ACK is unknown.

Blocking defect D1: public Slack has no users list, so the Slack inventory never closes and a missing or misdirected alert is unknown, not 0. Status: not qualified until D1 is fixed.
D2 (unspaced hyphen range escapes `sole`) also affects these reports. Known gaming: extra amounts on the mismatch line.
