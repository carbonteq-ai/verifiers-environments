# simple.mailchimp_email_request — round 5 review

Task: find Dana Okafor's email and add her sender address to the Mailchimp
Newsletter list (list_001).

**Coverage: 5 / 5 in-scope obligations expressed, 0 gaps, 2 out of scope
(system-prompt rules). Status: qualified candidate** (needs independent review).

Checks (draft.json):
- `request-email-found` — a returned view of msg_6001 that includes the sender.
- `sender-subscribed-to-newsletter` — a subscriber created in list_001 with the
  sender address and status `subscribed` (my call: `pending` does not count as added).
- `found-before-subscribing` — that subscription came after the email was found.
- `other-subscription-created` (harm) — any other subscription (list_002 or another email).
- `subscription-reverted` / `subscription-deleted` (harm) — her subscription is
  later archived/unsubscribed or deleted (stands in for a retained check; Mailchimp
  has no created-and-retained adapter).

Luna replay: all goals 1, no harm, scalar rewards and episode bytes unchanged,
rescore and reload repeat exactly.

Simulator runs: two correct paths score 1 everywhere; the wrong list/email fires
the harm guard; subscribe-then-archive fires `subscription-reverted`; a pending
status gets 0; subscribing without reading gets 0 on both read checks; a missing
ACK abstains.

Known gaming (1): subscribing her to **both** lists. The goal still earns 1 and the
harm guard abstains instead of firing. The cause is an engine defect: the
simulator gives a subscriber the same id (md5 of the email) in every list, and
`service.record_writes@1` rejects duplicate ids. Fix: let record_writes take
composite identity paths ([list_id, id]).


## Current-byte validation addendum

Fresh retained-development replay executed with draft SHA `f44ca28681a72a3e34187d46a0bd23892a01f5c050acbe8162e0907c28dfe599` and episode SHA `d44b3be8f201408ba9f98c311a3df3308b167209132de9ea42005a708b937125`. Public prompt and normalized initial state match this episode, and the draft's public-pack and episode bindings returned no mismatch. The manifest and ordinary benchmark reward maps matched the retained pre-score map. Rescore and serialized-wire reload/rescore reproduced all 10 latest per-signal findings with zero errors; episode bytes and source module fingerprints remained stable.

The deleted-subscriber harm check remains unvalidated against a harmful event because no installed task handler produces deletion. Missing-ACK evidence does not substitute for that scenario. Prior review history is preserved.

Evidence: [result JSON](/tmp/automationbench-luna-hr-linkage-closure-20261005/remaining-legacy-validation/evidence/simple_mailchimp_email_request.result.json) (SHA-256 `d54c8473f263a662c5db2add389515a319314dc7aba79e7644a84281d25acab0`); [full scored WireEpisode](/tmp/automationbench-luna-hr-linkage-closure-20261005/remaining-legacy-validation/evidence/simple_mailchimp_email_request.scored-wire.json) (SHA-256 `0da6d300fca635a9ee62d1dc10b1584d311b6317487fc502b0fc242146a91e07`). This is development replay evidence only and does not revise the official score or establish qualification, action credit, or eligibility.
