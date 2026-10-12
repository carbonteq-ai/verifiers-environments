# simple.sf_lead_employees_update

Public prompt: Update the number_of_employees field on Salesforce lead 00Q008 (Fatima Al-Rashid) to 250.

The draft binds the exact public system/user prompt and native-normalized initial Salesforce state. It checks requested_lead_retained_with_profile_preserved. No action credit is assigned.

Native replay on the retained episode matched public prompt and initial state; source bytes and scalar rewards stayed unchanged. Replay, rescore, and reload completed with zero errors.

Three real-handler controls are linked in review.json: a correct operation, a materially wrong value, and an ACK omitted from the serialized wire evidence. Missing ACK preserves any independently verified terminal outcome and abstains on action evidence. Ordinary-vs-manifest reward maps and reload parity are recorded for each control.

The original score of 1.0 is retained. Whole-task qualification and training eligibility are not granted.

## Re-review (shard 3)

Supersedes the earlier statement that no harm guard is asserted: guards are wrong-record-updated. Goals re-derived from the prompt and task data. Luna replay: 1/1 required goals met, 0 harms. No-op control (prompt, no tool calls): 0 goals met, 0 harms. Verdict: eval-ready.

Note: Retained/created-and-retained goals (where present) are not read by manifest_outcomes (no retained finding is produced in replay); the acknowledged-effect goal carries the requirement. Initial values differ from the requested ones, so a no-op cannot satisfy them.
