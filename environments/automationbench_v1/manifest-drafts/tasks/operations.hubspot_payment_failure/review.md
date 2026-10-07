# operations.hubspot_payment_failure — manifest review

**Status: not qualified.** 3 of 6 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; wrong-target harm {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; gaming {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; duplicate {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- Persisted retry-count update: Draft declares an update obligation, but native scorer abstains (`obligation_effect_scope_unavailable`) on both producer findings; the action credit is unsupported.
- All failed-payment contacts and retry policy: Only VIP contact 301 is represented; the complete retry selection and maximum/recovery policy is absent.
- Payment resolution and duplicate notice behavior: Alerts/email destination are checked without preventing duplicates or validating full payment context.

Non-1 replay findings: `vip-contact-retry-update=abstained:None (obligation_effect_scope_unavailable), vip-contact-retry-update=abstained:None (obligation_effect_scope_unavailable)`.

Retry-count update remains abstained (`obligation_effect_scope_unavailable`) even in the native correct sample; message findings are valid.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `feb3809edd8c0fc59c2614fd9f0ba0bdf7b55f398c67f4da71cc1926f922d56c`
Episode SHA-256: `72fc1f1b3706eb6264dff0733890d8f382608f5aade2a661645cb24599ef8f9a`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
