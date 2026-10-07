# simple.email_zendesk_ack_reply — batch-12 round-3 review (first draft)

Pack `batch-06.json` task 4; Luna episode `94a8e1ff…c7c9`. Whole task: **qualified candidate**.

**Coverage.** 5 in-scope obligations, all expressed; 0 gaps. Out of scope 4: 2 system-prompt rules and 2
`requires_judgement` (ticket describes the inquiry, reply acknowledges it; word-list checks removed).

**Draft** (6 outcome-only checks, no credit):
- `inquiry-email-read`: the agent saw the body of msg_3161 (Gmail read evidence).
- `read-before-ticket`, `read-before-reply`: some body read happened while no Legal ticket / no customer send
  existed yet (mechanism 8, `join == none`). Reading twice is fine.
- `legal-ticket-created`: new Zendesk ticket in the group named 'Legal Team' (grp_legal).
- `ticket-identifies-customer`: that ticket names the sender, Patricia Delgado, or has a requester created
  with her email (mechanism 8 join on the user created in the same call).
- `reply-to-customer`: a Gmail send or reply with legal@partnerco.example.com in To.
  A threaded reply is not required; a new 'Re:' email is accepted (Luna did this).

**Luna replay** (native scoring, rescore, reload): all 6 checks give 1. Bindings verified, no errors, scalar
rewards and episode bytes unchanged, findings repeated. Read coverage abstains (defect R1).

**Alternatives** (22 genuine-handler runs): 4 correct variants give 1 everywhere. Every harmful variant
(Support group, no group, wrong recipient, ticket without the customer, no read, acting before reading)
is a known 0 on its check, except 3 runs that also send mail: their read checks abstain (R1). Missing ACK
abstains. With the scratch R1 fix those 3 become known 0.

**Defect R1** (`repro_r1_read_scope_send.py`): the Gmail read adapter counts a send as a read that
changed Gmail, so read scope never closes in runs that send mail. Fix: skip audited send/reply handlers.
**Limitation J1** (`repro_j1_join_multiple_reads.py`): joins need exactly one match, so 'an earlier read
exists' is unknown after two reads. Avoided here by judging order on the read; an `exists` mode would help.

**Not checked by design.** Ticket wording and reply tone; a newsletter to the customer passes the reply check.
