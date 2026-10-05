# hr.docusign_severance_agreements: batch06 partial review

Original Luna score: 0.000000 (preserved); this is partial component evidence, not qualification.

Coverage: 4 expressed checks; 3 explicit gap(s); 2 shared system-prompt rules out of scope.

## Native replay

- No scorer errors; finding result repeats after rescore and wire reload: True/True.
- Original scalar rewards and source episode bytes unchanged: True/True.
- Findings are retained from the latest terminal assessment per run_id.

## Genuine-handler controls

- 5 scenarios; all ordinary-task vs manifest scalar reward maps equal: True; errors: 0.
- Gap: noncompete-legal-only-voiding (other:legal_action_target): Policy reserves voiding non-competes to Legal and explicitly says not to void directly; public state has no non-compete records or Legal action result, so task cannot establish voiding outcome.
- Gap: fatima-special-severance-terms (other:unsupported_template_fields): Fatima’s template identity is checked, but captured envelope fields do not establish that the enhanced template rendered the publicly authorized 15-week term.
- Gap: severance-message-count (report_fact_coverage): No check verifies the requested count in a message; content captures and task count relation are not expressed by the current checks.

No whole-task qualification, action credit, or downstream eligibility is claimed.
