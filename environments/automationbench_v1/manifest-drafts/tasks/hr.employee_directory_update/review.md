# hr.employee_directory_update: batch06 partial review

Original Luna score: 0.142857 (preserved); this is partial component evidence, not qualification.

Coverage: 4 expressed checks; 1 explicit gap(s); 2 shared system-prompt rules out of scope.

## Native replay

- No scorer errors; finding result repeats after rescore and wire reload: True/True.
- Original scalar rewards and source episode bytes unchanged: True/True.
- Findings are retained from the latest terminal assessment per run_id.

## Genuine-handler controls

- 3 scenarios; all ordinary-task vs manifest scalar reward maps equal: True; errors: 0.
- Gap: directory-summary-relevant-amounts (out_of_scope): The public changes sheet has no numeric amount field; the prompt’s “relevant amounts” has no supplied amount to include.

No whole-task qualification, action credit, or downstream eligibility is claimed.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.14285714285714285; draft changed vs. last commit: True.
- The termination goal read a record-write 'delete' source, but google_sheets_delete_row clears the row (an update whose operation is google_sheets_delete_row), so the goal could never be met by the real tool; it now reads the update and requires that operation on the terminated employee's directory row. The new-hire append, title-change update and #hr-general summary goals are kept. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/4 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 4/4, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `dce17ff7c1223d65d041044ab342553195613a174ac3bab75aa34622aba34325`.
