# hr.performance_feedback_logging — Luna manifest review

Whole task: **not_qualified** (3/5 in-scope obligations expressed; 2 gap(s)).

## Expressed checks (3)
- **structured-feedback-sm_fb_01** (`feedback-record-1`): Declared using task public rows and deterministic effect evidence.
- **structured-feedback-sm_fb_03** (`feedback-record-2`): Declared using task public rows and deterministic effect evidence.
- **structured-feedback-sm_fb_05** (`feedback-record-3`): Declared using task public rows and deterministic effect evidence.

## Gaps
- **notes-manager-attribution** [other:structured-extraction]: The current predicate vocabulary cannot parse the message’s delimited Employee/Rating/Notes fields into typed destination cells or authenticate the posting user’s manager name.
- **unstructured-message-exclusion** [report_fact_coverage]: Per-message required checks cover the three structured posts, but there is no check that the coffee, mention, reminder and unrelated posts are absent from appended rows.

## Luna replay
- `feedback-record-1`: valid=1.0 x1, inapplicable=None x7.
- `feedback-record-2`: inapplicable=None x7, valid=1.0 x1.
- `feedback-record-3`: inapplicable=None x7, valid=1.0 x1.
- Errors: 0; findings repeat/reload: True/True; scalar and episode bytes unchanged: True/True.

## Simulator and limits
- three structured ratings: All three required row writes scored 1.
- wrong rating: Affected feedback write scored 0.
- missing ACK: At least one write and coverage abstained.
- unstructured extra row: Extra unstructured row did not affect current checks; exclusion/coverage gap remains.
- Out of scope: system-no-clarifying-questions.
- Out of scope: system-list-only-acted-on.
- Source authority: public prompt and initial state; hidden assertions do not define requirements. Whole-task status remains not qualified while any in-scope obligation is a gap.
