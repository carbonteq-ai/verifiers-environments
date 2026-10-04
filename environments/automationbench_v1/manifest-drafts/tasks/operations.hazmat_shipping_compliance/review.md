# operations.hazmat_shipping_compliance — manifest review

**Status: not qualified.** 3 of 6 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:1.0:obligation_witnessed_required_effect': 6}; wrong-target harm {'valid:1.0:obligation_witnessed_required_effect': 6}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; gaming {'valid:1.0:obligation_witnessed_required_effect': 6}; duplicate {'valid:1.0:obligation_witnessed_required_effect': 6}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- All eligible shipments and sanctions/hold checks: Only SHP-801 is checked; the draft does not express full population selection or read-before-act compliance checks.
- Template and dispatch state: Envelope creation does not prove correct template, completion, or dispatch.
- Declared-value Q1 aggregate in email and Slack: Messages are checked for routing but not all shipment facts or aggregate declared value.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `72d5e3861f85c789c7e61c8263db80e1792aec192f4f26cecbc3ca986908f03f`
Episode SHA-256: `86d0561a447f4e62b964cf233dcf05beb802a56df383bcfbfeb65eb41ce94201`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
