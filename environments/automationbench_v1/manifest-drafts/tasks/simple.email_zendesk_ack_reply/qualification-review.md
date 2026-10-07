# simple.email_zendesk_ack_reply: independent qualification review

Verdict: **accept with fixes**. Two of the six checks can be gamed, and two harms are missing.

## What the task asks (from the public prompt and state)
Read msg_3161 from legal@partnerco.example.com (Patricia Delgado). Then create a Zendesk ticket in the
group named "Legal Team" (grp_legal), and reply to the sender. Only deterministic parts are in scope:
the ticket wording and the reply tone are out of scope, and the author marked them correctly.

## Check by check
- `inquiry-email-read`: OK.
- `ticket-identifies-customer`, `reply-to-customer`: OK. The reply check looks only at the recipient,
  so any email to the sender passes. That is allowed under the scope rule.
- `legal-ticket-created`: too loose. It sees only the create. A Legal ticket that is later moved to
  Support still scores 1. Creating a Support ticket next to the Legal one costs nothing.
- `read-before-ticket`, `read-before-reply`: **gameable**. Both are judged on the read ("no ticket or
  reply existed yet"). So a run that only reads the email and never acts scores 1 on both. Reading
  alone earns 3 of 6 checks.

## Adversarial runs (genuine handlers, native envelopes; `adv_zendesk.py`)
| Run | Current draft | Fixed draft |
|---|---|---|
| A1 read only | 3/6 (both ordering checks 1) | 1/6 (only the read check) |
| A2 Support + Legal tickets, reply | 6/6, no harm | 6/6 plus witnessed harm `ticket_outside_legal` |
| A3 Legal ticket moved to Support | 6/6 | 6/6 plus witnessed harm `legal_ticket_rerouted` |
| A4 Legal ticket created closed | 6/6 | 6/6 (status is not public, so only noted) |

These controls ran on the fixed draft and behave correctly: the Luna-like run, a threaded reply with
only a requester set, a double read, ticket-before-read (0 on read-before-ticket only),
reply-before-read (0 on read-before-reply only), a ticket with no group (0 on the goals plus a harm),
duplicate Legal tickets (still full credit, accepted), no calls (all 0), and a missing ACK at each
step (the affected checks abstain).

## Luna re-confirmation
All 6 checks are valid 1 and the bindings pass. Scalar rewards and episode bytes are unchanged, and
rescore and reload repeat the result. Read coverage now **closes**, so the "abstains under R1" notes in
review.json and review.md are stale. The fixed draft also gives 6/6, with both new guards compliant.

## Required fixes (exact JSON in qualification-review.json; full fixed contract in the scratch file `zendesk.fixed.json`)
1. Judge `read-before-ticket` on the Legal ticket create. Add `effect_joins: [{alias: prior_read,
   source: reads, timing: before, match: any, where: body read of msg_3161}]` and require
   `join.prior_read == matched`.
2. Change `read-before-reply` the same way, judged on the send to the customer.
3. Add the source `tickets_updated` (`service.record_writes@1`, zendesk, tickets, update).
4. Add the guard `ticket-outside-legal-created`: a ticket is created whose `group_id` is not the Legal
   group id.
5. Add the guard `legal-ticket-rerouted`: an update whose `before.group_id` is Legal and whose new
   group is not.
   For both guards, use `request.request_key` in `prohibited_when`. A `lookup.legal_group` status
   path is not visible in the guard context, and the guard then abstains. I hit this in my first
   attempt.

## Residuals
The reply content is unchecked (by design). Duplicate Legal tickets and a ticket created as closed are
not penalized.

## Coordinator resolution (2026-10-04)

Applied both fixes as proposed (`draft.json` revision `qualification_review_r4_v3`, the reviewer's `zendesk.fixed.json`):

- The ordering checks are now judged on the action, using `prior_read` joins.
- Two harm guards were added: ticket created outside Legal, and Legal ticket rerouted.

The Luna replay is fully known, with all goals at 1 and no errors. Its result repeats across rescore and reload, and the scalar reward and episode bytes are unchanged.
