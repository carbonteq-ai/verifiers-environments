# operations.equipment_lease_processing — manifest review

**Status: not qualified.** 3 of 6 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:1.0:obligation_witnessed_required_effect': 6}; wrong-target harm {'valid:1.0:obligation_witnessed_required_effect': 6}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; gaming {'valid:1.0:obligation_witnessed_required_effect': 6}; duplicate {'valid:1.0:obligation_witnessed_required_effect': 6}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- All eligible lease requests and budget/order: Only LR-401 is checked; the full eligibility, budget accumulation and ordering policy are not expressed.
- Envelope terms and duplicate/undo protection: Envelope-created check does not validate complete terms or prevent duplicate/void/recreated attempts.
- Complete requestor/procurement notice contents: Recipient/channel are checked without full lease fields and aggregate total.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `5d54b4b60cd0a509f6e7931a9d7c243fa55b23459f48541f8b55b7781b420814`
Episode SHA-256: `8e031cdde265e7467411402cc02713cd792ea5af74f625e1f37400bda1cd7f20`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
