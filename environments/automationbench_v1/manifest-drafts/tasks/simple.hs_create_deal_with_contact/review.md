# simple.hs_create_deal_with_contact (round 6)

Status: **qualified_candidate** — 5/5 in-scope obligations expressed, 0 gaps, 2 out of scope.

## Obligations

- O1-deal-created (goal, expressed, `deal-created`): objects.created_and_retained@1 over hubspot deals: a fresh deal with the exact name retained at the end.
- O2-amount (goal, expressed, `deal-amount`): Retained amount equals 50000 as a decimal.
- O3-stage (goal, expressed, `deal-stage`): Retained dealstage is the HubSpot id 'qualifiedtobuy' or the label 'Qualified to Buy'.
- O4-contact-association (goal, expressed, `deal-contact-associated`): hs_005 (bound from public contacts) in the retained deal's associated_contact_ids.
- O5-single-deal (guard, expressed, `duplicate-deal`): Harm: a second deal create with the same name (no HubSpot delete tool).
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: deal-amount=1.0, deal-contact-associated=1.0, deal-created=1.0, deal-stage=1.0, duplicate-deal=0.0.

## Simulator runs and gaming

H5 set stage to closedlost afterwards -> O3 0 (final-state check); C3 fix amount by update -> 1; H4 duplicate -> guard 1.
