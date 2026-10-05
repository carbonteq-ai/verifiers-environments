# simple.email_calendar_meeting_reply — batch 13 review

Public replay: f3a3cf63fc4611bf3986cdeee523a766d5d9be4f523829c22ce14d65ba04002e  
Draft: 2da4179c046cb0734a32c54b68288bdb7400770b1f4e930ac7c448239a7d623c

Coverage: 3 expressed, 1 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-source-email — Read the email
- **expressed — goal:** create-correct-calendar-event — Checks title, attendee, normalized UTC+05 start/end and prior returned read.
- **expressed — goal:** reply-to-client — The destination is checked; the response content is separately unavailable.
- **gap — report:** meeting-time-in-reply — The current send evidence does not yet check that the body states the requested time. In `src/automationbench_v1/contracts/predicates.py`, clock/date mentions establish only a lexical fact, not acceptance/confirmation; a deterministic semantic confirmation operator is needed while preserving equivalent valid time formats.

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
