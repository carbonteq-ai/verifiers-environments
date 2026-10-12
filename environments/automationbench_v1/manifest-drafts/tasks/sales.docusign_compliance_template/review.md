# sales.docusign_compliance_template

Draft SHA-256: `66eff5057357330771513b0837cac8ef060a243e78bed1cb063ac59152160901`.
Original retained score: 0.0 (official_zero); qualification not granted.

Genuine-handler controls use the complete public prompt, original assertion set, tool catalog, and independent ordinary/manifest trace fixtures. Actual numeric reward maps and check findings are recorded in `review.json` from the control artifact.

Variant findings:
- correct: reward maps equal=True; scorer errors=[]; correct_template=valid:1.0 (obligation_witnessed_required_effect), correct_template=valid:0.0 (obligation_required_effect_missing), correct_template=valid:0.0 (obligation_required_effect_missing), correct_template=valid:0.0 (obligation_required_effect_missing), correct_template=valid:0.0 (obligation_required_effect_missing).
- adverse: reward maps equal=True; scorer errors=[]; correct_template=valid:1.0 (obligation_witnessed_required_effect), correct_template=valid:0.0 (obligation_required_effect_missing), correct_template=valid:0.0 (obligation_required_effect_missing), correct_template=valid:0.0 (obligation_required_effect_missing), correct_template=valid:0.0 (obligation_required_effect_missing).
- missing_ack: reward maps equal=True; scorer errors=[]; correct_template=abstained:None (obligation_effect_scope_unavailable), correct_template=abstained:None (obligation_effect_scope_unavailable), correct_template=abstained:None (obligation_effect_scope_unavailable), correct_template=abstained:None (obligation_effect_scope_unavailable), correct_template=abstained:None (obligation_effect_scope_unavailable).

Known limitations and any unsupported public obligations remain listed in `known_gaps`; outcome evidence does not establish action credit or task qualification.

## Round-2 review D (ready)

Draft SHA-256 now `fa06446aa74ae24de4713546389ea6b581f34091c666d37e043e171bee7b0141`. The single goal matched envelopes through effect.record.custom_fields.deal_id, which no prompt or policy tells an agent to set (the benchmark identifies envelopes by signer). Split into one goal per closed deal (GermanTech GDPR, MedHealth HIPAA, CapitalBank SOC2, BigCorp Enterprise, StandardCo Standard, per the legal template-priority email) that requires the template id and the signers: primary signer for all, plus legal counsel for the GDPR/HIPAA/SOC2 deals as the policy email states; eligibility (Closed Won, no prior envelope, account found) kept from the original. Added harm: the StandardCo deal sent with a compliance template. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna replay: req 5 met 0 harms 0, noop clean; bindall []. Positive control (5 envelopes with the policy template and signers) meets 5/5, no harm. Multi-row population goals use match_cardinality per_candidate (a candidate-independent effect_match with unique_candidate leaves the goal undecided).
