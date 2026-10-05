# Review: operations.fire_suppression_testing

- **Status:** not qualified; retained Luna score 0.75 (official_partial).
- **Draft SHA-256:** `d3a93ae6c19bf01c567a76218774953aef1567531ed92a7a797cdb7f5314b82b`; retained episode SHA-256 `40cb1d65cfae1d7a82c72cfe454b5e840aa058c0ef2e0fb0ec318b4643da5efc`.
- **Coverage:** 4 expressed of 8 in-scope obligations; 4 gaps.
- Native score/rescore/reload parity: `True/True`; scalar/episode unchanged `True/True`.
- The Jira projection declares normalized action params under `effect.record.params.*`.
- No FIRE project exists in public initial state; exact creation returns `jira_project_not_found`, so positive and ticket-harm controls are unavailable.
- Technician SMS passes; coordinator email abstains. Full frequency/exception calculations and report totals remain unsupported.
