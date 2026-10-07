# operations.facebook_roas_monitoring — manifest review

**Status: not qualified.** 2 of 5 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:1.0:obligation_witnessed_required_effect': 4}; wrong-target harm {'valid:1.0:obligation_witnessed_required_effect': 4}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 2}; gaming {'valid:1.0:obligation_witnessed_required_effect': 4}; duplicate {'valid:1.0:obligation_witnessed_required_effect': 4}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- All active campaign anomaly selection: Only Retargeting is checked; active/paused scope and all anomalies/opportunities are not covered.
- Pause vs scale actions: The draft does not require the right action for every low/high ROAS campaign.
- Complete report and anomaly log: Alerts check one Slack and one email, not all required details or persistent log rows.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `cc33111c794fa897b8d9ea685e94b2af98c359b1bc2b6994e419b83be7e1c63a`
Episode SHA-256: `21730eb2cdfee04fe84e1f09a1bf38d3dde3b4149a0109631ffedbf087e5fdbb`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
