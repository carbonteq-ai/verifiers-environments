# operations.energy_consumption_anomaly — manifest review

**Status: not qualified.** 4 of 7 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:0.0:obligation_required_effect_missing': 4, 'valid:1.0:obligation_witnessed_required_effect': 4}; wrong-target harm {'valid:0.0:obligation_required_effect_missing': 4, 'valid:1.0:obligation_witnessed_required_effect': 4}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 6, 'valid:1.0:obligation_witnessed_required_effect': 2}; gaming {'valid:0.0:obligation_required_effect_missing': 4, 'valid:1.0:obligation_witnessed_required_effect': 4}; duplicate {'valid:0.0:obligation_required_effect_missing': 4, 'valid:1.0:obligation_witnessed_required_effect': 4}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- Derive anomaly population from config and readings: The draft encodes two expected findings rather than computing threshold and completeness for all buildings.
- No report for incomplete/non-anomalous buildings: No prohibited-effect guard blocks naming ineligible buildings.
- Strict verbatim values and rival-value resistance: The checks require the selected facts together but do not rule out rival numeric values or require the config threshold to be cited.

Non-1 replay findings: `hq-tower-slack-facts=valid:0.0 (obligation_required_effect_missing), hq-tower-slack-facts=valid:0.0 (obligation_required_effect_missing), hq-tower-email-facts=valid:0.0 (obligation_required_effect_missing), hq-tower-email-facts=valid:0.0 (obligation_required_effect_missing)`.

Public-derived two-decimal HQ values pass the correct simulator variant, while Luna’s longer equivalent decimals miss the verbatim match. This is a numeric precision limitation; see the reproducer and mechanism gap in review.json.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `6e08d83e4249fb8e2579db932b447ad9e9be1bcb418aef2ee3347942289e4900`
Episode SHA-256: `418cf12cb4c6c7bba777d05d117be913e8aadb86df9c7f3cac6415ab58748df1`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
