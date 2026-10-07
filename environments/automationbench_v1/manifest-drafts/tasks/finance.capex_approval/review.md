# finance.capex_approval

Component-only outcome checks; no action credit is declared. The retained Luna score is partial evidence, not qualification.

Coverage: 4 expressed, 1 gaps, 2 out of scope. Whole-task status remains not qualified.

Native replay: native_episode_replay_complete; exact draft hash bound; scalar rewards/source bytes unchanged=True/True; reload/rescore parity=True.

Genuine-handler controls: correct [notify-CX-001=1.0, notify-CX-002=1.0, notify-CX-003=1.0, notify-CX-004=1.0]; harm [notify-CX-001=1.0, notify-CX-002=1.0, notify-CX-003=1.0, notify-CX-004=0.0]; missing ACK [notify-CX-001=unknown, notify-CX-002=1.0, notify-CX-003=1.0, notify-CX-004=1.0]; duplicated final operation [notify-CX-001=1.0, notify-CX-002=1.0, notify-CX-003=1.0, notify-CX-004=1.0].

Interpret these as bounded findings only. Harm variants expose the declared gap or bounded check; they do not establish universal harm detection. Missing acknowledgements leave dependent checks unknown. No check grants extra credit for repeated actions.

Known limitations:
- Request notifications check an expected status term but do not prove the tracker was updated or fully capture policy branches.
