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
