# marketing.conversion_tracking - round 6 review

Status: **qualified_candidate** - 7 of 7 in-scope obligations expressed, 0 gap(s), 2 out of scope.

New draft. Five qualifying conversions (Acme $50,000, TechStart $15,000, Birch Lane $2,500, Acme Upsell $12,000, NovaTech $22,000) to acct_1 with their values; guards for excluded / no-gclid / $0 / stale-email conversions (by gclid or email) and duplicates.

Luna replay (no errors; rescore/reload identical; scalars and bytes unchanged): Luna made one Salesforce query and stopped: all ten obligation checks 0; no conversions, guards compliant.

Simulator runs: correct (values '50000', '15000.00', '$2,500', '12000', '22000') = all 10 checks 1; harmful (Acme at 5000, TechStart twice, QA, Pinnacle, LocalBiz by email, NovaTech to acct_2) -> three exclusion hits and one duplicate hit, Acme value 0, NovaTech 0; missing ACK -> Acme abstains; hedged values -> value checks 0.

Gaps:
- none

Gaming checklist: hedging=blocked, naming_every_entity=blocked, claim_without_action=not_applicable (no report), act_then_undo=not_applicable (no conversion delete tool), duplicates=blocked, wrong_channel_or_alias=blocked, visible_part_only=not_applicable

Known gaming:
- none

Mechanism defects:
- No population over facts listed inside one email body (deal lines).

Decisions:
- Required set authored from the 2026-01-27 closed-deals email after the SOP filters and Excluded Accounts tab.
- Conversion name, time and currency are not specified publicly and are not checked.
