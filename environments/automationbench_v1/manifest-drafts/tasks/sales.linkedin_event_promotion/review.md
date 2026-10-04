# sales.linkedin_event_promotion (round 6)

Promote the 'AI Transformation in Enterprise' webinar (March 5, 2026, registration URL) to Salesforce contacts
whose industry and seniority match: message existing LinkedIn connections, invite others, record outreach
status, summarize in #marketing-outreach. Distractors: a March 12 webinar email, a connected lead, 45
compliance-hold contacts, look-alike LinkedIn profiles.

Expressed (6/6 in scope): Rachel Kim (connected) gets a LinkedIn message; it carries topic, date and URL and
no March 12 date; Marcus Lee (not connected) gets a connection request; each has an outreach status (contact
update, note or task) tied to real outreach; the #marketing-outreach post names each after outreach; one
any-channel guard on outreach to anyone else. Out of scope: status/summary wording, the optional invite
note, system-prompt rules.

Luna did the task correctly (status as Salesforce notes): every goal 1, guard 0, no errors; scalars, bytes,
rescore and reload unchanged.

Simulator runs: correct and notes/profile-id variants score 1 everywhere; messaging a lead and a held contact's
profile, inviting noise, or emailing the Retail VP fire the guard per extra recipient; a March 12 hedge fails the
facts check; statuses/summary without outreach score 0; swapped action types fail the two action goals; missing
ACKs give unknown. Mechanism defect: id-less public LinkedIn connections cannot form a population, so the
connection set is declared. Status: qualified candidate.
