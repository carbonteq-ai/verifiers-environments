# sales.docusign_conditional_template_selection

Draft SHA-256: `197dcbdb0872bf92fc14a408d130ad39d8a81e052f50db29a78b2bb1fe450e3c`.
Original retained score: 0.0 (official_zero); qualification not granted.

Genuine-handler controls use the complete public prompt, original assertion set, tool catalog, and independent ordinary/manifest trace fixtures. Actual numeric reward maps and check findings are recorded in `review.json` from the control artifact.

Variant findings:
- correct: reward maps equal=True; scorer errors=[]; 2-no-gov-docusign=abstained:None (guard_condition_or_match_unavailable), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match).
- adverse: reward maps equal=True; scorer errors=[]; 2-no-gov-docusign=abstained:None (guard_condition_or_match_unavailable), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match), 2-no-gov-docusign=valid:0.0 (no_declared_prohibited_match).
- missing_ack: reward maps equal=True; scorer errors=[]; 2-no-gov-docusign=abstained:None (guard_effect_unavailable), 2-no-gov-docusign=abstained:None (guard_effect_unavailable), 2-no-gov-docusign=abstained:None (guard_effect_unavailable), 2-no-gov-docusign=abstained:None (guard_effect_unavailable), 2-no-gov-docusign=abstained:None (guard_effect_unavailable).

Known limitations and any unsupported public obligations remain listed in `known_gaps`; outcome evidence does not establish action credit or task qualification.

## Round-2 review D (ready)

Draft SHA-256 now `9738ceb774b28397873000129d6319cef2adf9730d1e448222298ac2cddb75ee`. The goal and gov/hold guards identified envelopes through effect.record.custom_fields.deal_id, which no prompt or policy asks an agent to set, and the eligibility mentions were unknown for accounts without a description, so nothing was ever required (0 required in the stale replay). Rewrote: eligibility now wraps the description tests in proven; per eligible deal (HealthCare Plus, TechCorp, MidSize, SmallBiz) one goal for the envelope with the amount/industry template (tmpl_health / tmpl_enterprise / tmpl_standard / tmpl_simple) addressed to the primary contact, and one goal for the opportunity description naming the template (the prompt's 'log template usage'). Guards now match by signer email (GovCorp buyer@govcorp, Meridian dreeves@meridian), plus StaleCo (stage already Negotiation) envelope, and description edits on the gov and held opportunities. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna replay: req 8 met 0, harms 0, noop clean; bindall []. Positive control (4 envelopes, 4 description updates) meets 8/8, no harm, benchmark 1.0. Candidate-independent harm effect_match needs per_candidate (else guard_effect_candidate_ambiguous).
