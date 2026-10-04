# operations.google_ads_budget_alert — manifest review

**Status: not qualified.** 3 of 4 in-scope obligations are expressed; 2 remain. System communication style is out of scope.

Luna official score: 0.875 (official_partial); this outcome does not establish action credit or token-level support. Native replay errors=0; rescore/reload/scalar/source bytes unchanged = True/True/True/True.

Native simulator correct/harm/missing-ACK/gaming variants ran through actual handlers. Correct: {'brand-awareness-campaign-paused|valid|1.0|obligation_witnessed_required_effect': 2, 'ads-budget-director-email|valid|1.0|obligation_witnessed_required_effect': 2, 'brand-awareness-budget-log|abstained|None|obligation_effect_scope_unavailable': 2}; harm: {'brand-awareness-campaign-paused|valid|1.0|obligation_witnessed_required_effect': 2, 'ads-budget-director-email|valid|1.0|obligation_witnessed_required_effect': 2, 'brand-awareness-budget-log|abstained|None|obligation_effect_scope_unavailable': 2}; missing ACK: {'brand-awareness-campaign-paused|abstained|None|obligation_effect_scope_unavailable': 2, 'ads-budget-director-email|valid|1.0|obligation_witnessed_required_effect': 2, 'brand-awareness-budget-log|abstained|None|obligation_effect_scope_unavailable': 2}; gaming: {'brand-awareness-campaign-paused|valid|1.0|obligation_witnessed_required_effect': 2, 'ads-budget-director-email|valid|1.0|obligation_witnessed_required_effect': 2, 'brand-awareness-budget-log|abstained|None|obligation_effect_scope_unavailable': 2}.

Gaps:
- campaign classification and threshold math: Only Brand Awareness Q1 is checked against the public projection calculation ($2,900 + 5 x $100 > 110% of $3,000). The draft does not classify every active campaign, distinguish warning from critical action, or close paused campaigns.
- all-alert log scope: A Sheets append check is declared but native replay abstained with obligation_effect_scope_unavailable for the initially empty alerts worksheet; all log rows remain unverified.

Only public prompt and initial state establish requirements. Retained write arguments were replay stimuli only. Out-of-scope wording is not included in whole-task coverage.

Draft SHA-256: `7478da0da84bfd759d519e283fff3ac5e4775e5167ef3a0dae4a581c2778671c`
Episode SHA-256: `2e3b139ccfea24004fe2a1f6a86bd1bd1b7ccb4ddfa867e74ada8cf901293e1a`
