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
