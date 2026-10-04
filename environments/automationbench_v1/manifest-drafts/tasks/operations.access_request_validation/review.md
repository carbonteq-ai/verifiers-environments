# operations.access_request_validation — manifest review

**Status: not qualified.** 3 of 5 in-scope obligations are represented; 2 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:0.0:no_declared_prohibited_match': 6, 'valid:1.0:obligation_witnessed_required_effect': 4}; wrong-target harm {'valid:0.0:no_declared_prohibited_match': 6, 'valid:1.0:witnessed_declared_prohibited_effect': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; missing ACK {'abstained:None:guard_effect_unavailable': 2, 'valid:0.0:no_declared_prohibited_match': 4, 'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 2}; gaming {'valid:0.0:no_declared_prohibited_match': 8, 'valid:1.0:obligation_witnessed_required_effect': 4}; duplicate {'valid:0.0:no_declared_prohibited_match': 8, 'valid:1.0:obligation_witnessed_required_effect': 4}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- Approved-vs-denied application complete handling: The draft checks the approved provisioning task and denial notice, but does not prevent provisioning or other access changes for denied applicants.
- Application-specific required fields and all candidates: Only Jordan Lee is covered; no all-applicant selection or requested access scope/expiry constraints are checked.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `5d6e5c13faf5e47a03e580d29a971ebe6bc264fe169e351074403297a788e667`
Episode SHA-256: `b73ff019d1cbff99dee848574dffd0c844c45e846316181e5f78a284260deb0d`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
