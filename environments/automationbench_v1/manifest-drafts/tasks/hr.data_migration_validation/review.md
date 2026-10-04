# hr.data_migration_validation — Luna manifest review

Whole task: **not_qualified** (2/4 in-scope obligations expressed; 2 gap(s)).

## Expressed checks (2)
- **correction-EMP-6601** (`migration-correction-1`): Declared using task public rows and deterministic effect evidence.
- **correction-EMP-6618** (`migration-correction-2`): Declared using task public rows and deterministic effect evidence.

## Gaps
- **tracker-validation-status** [other:status-semantics]: The request does not give public status values for validated and discrepancy rows, so a manifest cannot safely invent them.
- **all-records-validated** [cross_system_reconciliation]: The one HRIS email only contains corrections for two IDs; it does not assert current canonical values for all remaining employee fields.

## Luna replay
- `migration-correction-1`: valid=1.0 x1, inapplicable=None x7.
- `migration-correction-2`: inapplicable=None x7, valid=1.0 x1.
- Errors: 0; findings repeat/reload: True/True; scalar and episode bytes unchanged: True/True.

## Simulator and limits
- correct corrections: Two required correction emails were witnessed; other records inapplicable.
- wrong correction: Incorrect EMP-6601 correction scored 0.
- missing ACK: Both correction outcomes and coverage abstained.
- extra unverified record: An added EMP-6655 statement did not invalidate required corrections; validation/all-record coverage gap remains.
- Out of scope: system-no-clarifying-questions.
- Out of scope: system-list-only-acted-on.
- Source authority: public prompt and initial state; hidden assertions do not define requirements. Whole-task status remains not qualified while any in-scope obligation is a gap.
