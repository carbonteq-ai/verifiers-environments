# operations.mailroom_package_routing — manifest review

**Status: not qualified.** 3 of 6 in-scope obligations are represented; 3 gaps remain. The two out-of-scope items are communication-style and judgement-only language.

Luna official score: 1.0 (official_full). Native replay: errors=0; rescore/reload/scalar/source-byte parity = True/True/True/True.

Native simulator variants through genuine handlers: correct sample {'valid:0.0:no_declared_prohibited_match': 4, 'valid:1.0:obligation_witnessed_required_effect': 4}; wrong-target harm {'valid:0.0:no_declared_prohibited_match': 4, 'valid:1.0:witnessed_declared_prohibited_effect': 2, 'valid:1.0:obligation_witnessed_required_effect': 4}; missing ACK {'abstained:None:guard_effect_unavailable': 2, 'valid:0.0:no_declared_prohibited_match': 2, 'abstained:None:obligation_effect_scope_unavailable': 2, 'valid:1.0:obligation_witnessed_required_effect': 2}; gaming {'valid:0.0:no_declared_prohibited_match': 6, 'valid:1.0:obligation_witnessed_required_effect': 4}; duplicate {'valid:0.0:no_declared_prohibited_match': 6, 'valid:1.0:obligation_witnessed_required_effect': 4}.
Retained episode write args served only as simulator stimuli, not as authority for requirements or whole-task correctness. All variants preserved scalar rewards; see `sim_all.json` in scratch.

Gaps:
- Join identity, department, and routing policy for all packages: Draft addresses TRK-90001 but does not cover every eligible package or join recipient name/department.
- Termination, leave, oversized, and hazardous holds: No prohibited-effect guards cover recipients or packages that policy excludes/holds.
- Complete floor/exception summary: Slack existence is checked without full routing list, floor details, or exception totals.

The variants check only expressed obligations. Official outcome, action credit, and token support remain distinct; whole-task coverage is incomplete.

Draft SHA-256: `8b2dcd23eef64389449ba4314321630f73ac4c0e27b423ef0b41e3571ac39a24`
Episode SHA-256: `84426e827781a7eaeb78f0a980bd7fdd89110cb7125d2ba820f2b7d998300ff1`
Environment HEAD: `f7790acf30089be7909f42bd779c5d10e9a4b289`
