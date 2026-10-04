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
