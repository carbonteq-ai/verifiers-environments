# support.zendesk_cross_org_merge

The existing partial retained-ticket component now derives the destination from the matched public `ws_candidates` row: each candidate ticket’s initial `organization_id` joins `Source Org ID`, then the terminal ticket organization is compared with that row’s `Target Org ID`. The public eligibility predicate remains narrowly limited to the previously supported source organization. No eligibility expansion or priority choice was introduced.

The amended draft passes native contract loading and replay with exact public prompt/initial binding, unchanged reward and source episode bytes, successful wire dump/reload, and matching post-reload findings. The two candidate tickets remain at a terminal destination that does not satisfy the public row target; tickets without an organization id remain unknown. Existing replay history is retained in `validation_history`.

Whole-task status: `not_qualified`. Do-not-merge exclusions, full source/target group reconciliation, relevant amounts, the actual organization merge operation and summary completeness remain gaps.
