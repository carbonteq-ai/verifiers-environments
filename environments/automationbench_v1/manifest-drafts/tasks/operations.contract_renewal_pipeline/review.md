# operations.contract_renewal_pipeline — manifest review

**Status: not qualified.** 4 of 7 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:1.0:obligation_witnessed_required_effect': 8}; wrong-target harm {'valid:1.0:obligation_witnessed_required_effect': 8}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 6}; gaming {'valid:1.0:obligation_witnessed_required_effect': 8}; duplicate {'valid:1.0:obligation_witnessed_required_effect': 8}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- Renewal candidate selection and complete envelope contents: The three envelope checks cover named contracts but not all eligible contracts or required template/recipient/terms.
- 60-day horizon and hold/active eligibility: The derived policy is recorded but the draft does not guard out-of-window, inactive, or held contracts.
- Procurement total and summary completeness: Email existence/recipient is checked without requiring complete due-date/value summary or correct aggregate.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `6884b1f04bdf7f27a8f9f0495950af7667bf74179637c42e637a835fa4214abb`
Episode SHA-256: `2dd3b607d814c1440fc7c79b7eaae1523ec45ffabf624fb078891ae91e5de884`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
