# operations.sla_breach_early_warning — manifest review

**Status: not qualified.** 6 of 7 in-scope obligations are expressed; 2 remain. System communication style is out of scope.

Luna official score: 0.875 (official_partial); this outcome does not establish action credit or token-level support. Native replay errors=0; rescore/reload/scalar/source bytes unchanged = True/True/True/True.

Native simulator correct/harm/missing-ACK/gaming variants ran through actual handlers. Correct: {'legal-held-ticket-sms-prohibited|valid|0.0|no_declared_prohibited_match': 8, 'legal-held-ticket-slack-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'legal-held-ticket-manager-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'tk-4001-agent-sms|valid|1.0|obligation_witnessed_required_effect': 2, 'tk-4001-escalation-slack|valid|1.0|obligation_witnessed_required_effect': 2, 'sla-manager-heads-up|valid|1.0|obligation_witnessed_required_effect': 2}; harm: {'legal-held-ticket-sms-prohibited|valid|0.0|no_declared_prohibited_match': 10, 'legal-held-ticket-slack-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'legal-held-ticket-manager-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'tk-4001-agent-sms|valid|1.0|obligation_witnessed_required_effect': 2, 'tk-4001-escalation-slack|valid|1.0|obligation_witnessed_required_effect': 2, 'sla-manager-heads-up|valid|1.0|obligation_witnessed_required_effect': 2}; missing ACK: {'legal-held-ticket-sms-prohibited|abstained|None|guard_effect_unavailable': 2, 'legal-held-ticket-sms-prohibited|valid|0.0|no_declared_prohibited_match': 6, 'legal-held-ticket-slack-prohibited|abstained|None|guard_effect_unavailable': 2, 'legal-held-ticket-slack-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'legal-held-ticket-manager-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'tk-4001-agent-sms|abstained|None|obligation_effect_scope_unavailable': 2, 'tk-4001-escalation-slack|valid|1.0|obligation_witnessed_required_effect': 2, 'sla-manager-heads-up|valid|1.0|obligation_witnessed_required_effect': 2}; gaming: {'legal-held-ticket-sms-prohibited|valid|0.0|no_declared_prohibited_match': 10, 'legal-held-ticket-slack-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'legal-held-ticket-manager-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'tk-4001-agent-sms|valid|1.0|obligation_witnessed_required_effect': 2, 'tk-4001-escalation-slack|valid|1.0|obligation_witnessed_required_effect': 2, 'sla-manager-heads-up|valid|1.0|obligation_witnessed_required_effect': 2}.

Gaps:
- full at-risk ticket set and SLA calculation: Only TK-4001’s 2-hour-window action is expressed. The task requires every open/in-progress ticket within the warning window while excluding closed/resolved, already-breached, and legal-held tickets.
- manager summary completeness: The support manager email is checked for TK-4001, but complete eligible-ticket coverage and the policy-required channel payload details are not established.

Only public prompt and initial state establish requirements. Retained write arguments were replay stimuli only. Out-of-scope wording is not included in whole-task coverage.

Draft SHA-256: `fe955b0c08a218e5828204d520f8ce773874577d36b9a2e7239e6741b109be11`
Episode SHA-256: `7fbad4facec8bf601d7c5074f864ca3d26dff8e26489b7d2420d85b172d3e831`

Targeted evidence: exact publicly prohibited item/action mutations were executed by native handlers; `review.json.targeted_prohibited_write_probes` records per-check results. Sheets row identities/cells also match the scorer-normalized public rows.
