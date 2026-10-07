# hr.expense_policy_violation

Partial component authoring only; whole-task status: not qualified.
- Original reference outcome: official_zero; score [{'name': 'partial_credit', 'score': 0.0, 'weight': 1.0}].

- Source episode SHA-256: `3cf9563520cb6bd61d33c4113ce769da22cdb4379867ecfcf611113d451ced01`
- Draft SHA-256: `b6fc9d72a1b1c192d02848b01b9d47db1b5d0fc184c9ab2f1859409c44f48fe9`
- Native replay: no errors; rescore/reload stable; scalar rewards and source bytes unchanged.
- Expressed checks: bob-no-receipt-status-updated, bob-manager-notified-of-receipt-violation, preapproved-carol-expense-not-flagged.
- Genuine-handler controls: 3 scenarios; ordinary-vs-manifest scalar parity: all equal.
- Limitations:
  - complete approval decision across every pending report: Current checks express Bob’s missing-receipt violation only. Other pending rows and the exact under-$100 exception request must retain the task’s public policy distinctions; the source does not resolve team-dinner per-person amount.
