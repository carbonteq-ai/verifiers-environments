# simple.email_sf_contact_assistant_update — round 5 review

Task: find Rachel Nguyen's email and set her contact's assistant name and email.
This extends the installed `contact-assistant-update.json`: the installed checks,
sources, bindings and credit are unchanged, and new checks are appended.

**Coverage: 7 / 7 in-scope obligations expressed, 0 gaps, 2 out of scope.
Status: qualified candidate** (needs independent review).

New checks: read before the assistant update (joined on the installed `message_reads`
source); harm when the update changes Rachel's name, email, phone, title or account
fields (e.g. Kevin's address written into Rachel's own email); harm when another
contact is updated, a duplicate Rachel contact is created, or 003010 is deleted.
A separate contact for Kevin is not penalized (my call).

Luna replay: all goals 1 and both installed credits granted, no harm, rewards and
bytes unchanged; findings and credit repeat.

Simulator runs: contact_update and update_record paths both pass; overwriting
Rachel's email fires the field guard and `requested_state` scores 0; a duplicate
Rachel contact fires its guard; update-before-read scores 0 on ordering; a missing
ACK abstains.

Known gaming (1): write blind, then read and re-write. `read-before-update` passes
because the join accepts any later write. Fix: judge ordering on the first target write.

Defect (pre-existing, also on the installed contract): rescore adds a duplicate
obligation scope receipt with a new input digest. Findings and credit repeat.
