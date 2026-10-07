# sales.cross_platform_account_health_score (batch04)

The contract reads the scoring and classification policy, checks the #account-health destination, and requires the three explicitly named Enterprise accounts in the posted summary. The reference summary is provisional and calls out missing linked usage, billing and support evidence. The score itself cannot be checked per account from the current declaration; cross-platform joins and missing score inputs remain unresolved.

Original Luna score: 0.300000 (official_partial). Native replay found 12 findings, no errors; source bytes and scalar rewards were unchanged, serialized reload/rescore findings matched.

Coverage: 3 expressed components; 2 gaps; 2 out of scope. Whole-task status: **not qualified**.

Limitations: Per-account scoring needs matching Zoom attendees to Salesforce contacts/accounts, LinkedIn relationships, email activity and task/opportunity state, then weighting the joined signals. `population.aggregate@1` / `collections.counts_when@1` can aggregate within one collection, but no existing typed declaration correlates those heterogeneous child collections by parent account. Moreover, the public snapshot lacks linked usage, billing and support signals; unknowns must not be treated as zero. Root should treat this as a per-member cross-population aggregation candidate; no numeric score was invented.

Simulator controls: native read of Signal Weights: scoring_policy_read=1; native read of Classification Thresholds: classification_policy_read=1; correct account-health message with the three named accounts: requested_channel_summary=1; same account summary sent to wrong channel: requested_channel_summary=0; missing ACK on summary send: message obligation abstains unknown.
