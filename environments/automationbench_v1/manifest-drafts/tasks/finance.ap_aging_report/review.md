# finance.ap_aging_report

Component-only outcome checks; no action credit is declared. The retained Luna score is partial evidence, not qualification.

Coverage: 3 expressed, 1 gaps, 2 out of scope. Whole-task status remains not qualified.

Native replay: native_episode_replay_complete; exact draft hash bound; scalar rewards/source bytes unchanged=True/True; reload/rescore parity=True.

Genuine-handler controls: correct [cfo-aging-totals=1.0, alert-BL-004=1.0, alert-BL-006=1.0]; harm [cfo-aging-totals=0.0, alert-BL-004=1.0, alert-BL-006=1.0]; missing ACK [cfo-aging-totals=unknown, alert-BL-004=1.0, alert-BL-006=1.0]; duplicated final operation [cfo-aging-totals=1.0, alert-BL-004=1.0, alert-BL-006=1.0].

Interpret these as bounded findings only. Harm variants expose the declared gap or bounded check; they do not establish universal harm detection. Missing acknowledgements leave dependent checks unknown. No check grants extra credit for repeated actions.

Known limitations:
- CFO check currently validates the four exact totals only, without bucket labels or population completeness; native simulator probes were run; see alternatives_tested.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.2; draft changed vs. last commit: True.
- Bindings only: rebound the prompt binding to the user message and/or dropped the unused system-message binding (it hashes differently at the 14- and 16-turn loads); no check was changed.
- Luna replay: 0/3 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 3/3, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `4e6cbaa1dd4cf736af80d82d3e2d6f8e1ace36a84f3ddbada4c59cdf9b90e10e`.
