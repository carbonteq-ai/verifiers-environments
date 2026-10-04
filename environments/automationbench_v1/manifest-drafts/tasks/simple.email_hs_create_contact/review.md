# simple.email_hs_create_contact — round 5 review

Task: find Nathan Brooks's introduction email and create a HubSpot contact with his info.

**Coverage: 10 / 10 in-scope obligations expressed, 0 gaps, 2 out of scope.
Status: qualified candidate** (needs independent review).

Checks: body read of msg_3042; a created contact with the sender email; on that
contact, name (first/last fields or "Nathan Brooks" in any field), company
"PineGrove Analytics", title "Head of IT", and phone (`555-4242` verbatim) in any
field value; read before create; the contact is still there at the end (email + last
name); harm guards for a duplicate contact with the same email, and for a contact
created with some other non-empty email.

Luna replay: everything 1, no harm, rewards/bytes unchanged, rescore/reload repeat.

Simulator runs: Luna-like and an alternative (name aliases, company only in a custom
property, phone `555-4242`) both pass. A fabricated-email contact plus duplicates fires both
guards. Creating before reading with facts missing gets 0 on read-order, company,
title and phone. A missing ACK abstains on the effect checks.

Known gaming (1): put only the email in the contact and paste the whole email body
into one custom property. The name, company, title and phone checks all pass
because they accept a mention in any field; only `contact-retained` (last-name field)
catches it. Fix: check the dedicated HubSpot fields.

Limitation: phone formats without the `555-4242` group (e.g. "+1 555 4242") read as false.
