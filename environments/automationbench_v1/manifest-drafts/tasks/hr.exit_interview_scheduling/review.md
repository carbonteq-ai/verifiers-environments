# hr.exit_interview_scheduling — Luna manifest review

Whole task: **not_qualified** (8/9 in-scope obligations expressed; 1 gap(s)).

Prior review retained: Prior evidence retained: Rosa’s email named Derek as invited but omitted him; scalar 0.8889 and 14 prior simulator runs remain in review.json..

## Expressed checks
- 8 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- interview-five-business-days-before [other:date_mention]: Calendar path expressed: start date (UTC) = add_business_days(Last Day, -5, holidays) with both weekend readings accepted, ASAP window when the target has passed, and a guard join against other future-dated events for the same employee. Email path (the only listed tool is Gmail): a computed date cannot be mentioned (MentionTerm has no date mode; a derived calendar_date is predicate_mentions_value_unavailable, R4-L2), so an email invite leaves the date unknown (correct_email_invites_only abstains).

## Native replay
- 6 checks replayed; 0/abstentions observed in: involuntary-interview-calendar-event, roster-pii-sent-to-vendor, interview-invite-employee-and-manager, interview-date-five-business-days-before; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
