# simple.sf_create_followup_task

Public prompt: Create a Salesforce task for a follow-up call with Jordan Lee (contact 003001). Set the due date to 2026-02-28 and subject to 'Follow-up call with Jordan Lee'.

The draft binds the exact public system/user prompt and native-normalized initial Salesforce state. It checks requested_acknowledged_writes, requested_object_created_and_retained. No action credit is assigned.

Native replay on the retained episode matched public prompt and initial state; source bytes and scalar rewards stayed unchanged. Replay, rescore, and reload completed with zero errors.

Three real-handler controls are linked in review.json: a correct operation, a materially wrong value, and an ACK omitted from the serialized wire evidence. Missing ACK preserves any independently verified terminal outcome and abstains on action evidence. Ordinary-vs-manifest reward maps and reload parity are recorded for each control.

The original score of 1.0 is retained. Whole-task qualification and training eligibility are not granted.
