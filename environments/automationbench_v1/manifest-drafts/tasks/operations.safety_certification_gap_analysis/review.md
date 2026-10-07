# operations.safety_certification_gap_analysis — manifest review

**Status: not qualified.** 4 of 5 in-scope obligations are expressed; 2 remain. System communication style is out of scope.

Luna official score: 1.0 (official_full); this outcome does not establish action credit or token-level support. Native replay errors=0; rescore/reload/scalar/source bytes unchanged = True/True/True/True.

Native simulator correct/harm/missing-ACK/gaming variants ran through actual handlers. Correct: {'leave-exempt-report-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'james-forklift-expired-jira|valid|0.0|obligation_required_effect_missing': 2, 'safety-audit-coordinator-email|valid|1.0|obligation_witnessed_required_effect': 2}; harm: {'leave-exempt-report-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'james-forklift-expired-jira|valid|0.0|obligation_required_effect_missing': 2, 'safety-audit-coordinator-email|valid|1.0|obligation_witnessed_required_effect': 2}; missing ACK: {'leave-exempt-report-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'james-forklift-expired-jira|abstained|None|obligation_effect_scope_unavailable': 2, 'safety-audit-coordinator-email|valid|1.0|obligation_witnessed_required_effect': 2}; gaming: {'leave-exempt-report-email-prohibited|valid|0.0|no_declared_prohibited_match': 2, 'james-forklift-expired-jira|valid|0.0|obligation_required_effect_missing': 2, 'safety-audit-coordinator-email|valid|1.0|obligation_witnessed_required_effect': 2}.

Gaps:
- role requirements cross-reference: The task requires comparing every employee certification to role requirements and checking both missing and expired required certificates. The draft checks James Parker’s expired Forklift License only; record absence/role joins and leave-exempt employee filtering remain uncovered.
- complete per-employee Jira issue and report: A coordinator email is checked for James Parker, but per-employee issue completeness and the complete audit report are not proven; native replay did not witness the expressed James issue.

Only public prompt and initial state establish requirements. Retained write arguments were replay stimuli only. Out-of-scope wording is not included in whole-task coverage.

Draft SHA-256: `5828620a527ce068cbd9d70e0eec5164c7766351b76ae00319a50c29daf3285b`
Episode SHA-256: `82b70841347b8f1fc6fbfde846eb48160f5785e4dc687abcb9eb66e3388078a9`

Targeted evidence: exact publicly prohibited item/action mutations were executed by native handlers; `review.json.targeted_prohibited_write_probes` records per-check results. Sheets row identities/cells also match the scorer-normalized public rows.

Jira project SAFE is absent from the public simulator state; native create returns `jira_project_not_found`. Jira issue completion and its leave-exemption guard are therefore unsupported here.
