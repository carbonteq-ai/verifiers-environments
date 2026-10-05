# hr.termination_checklist — component review

Draft `batch09_partial_v2`: 39 checks (4 harmful-action guards); outcome-only, no action credit asserted.

- Original Luna class/score: `recorded_partial_score` / `0.0`; original reward entries retained in review.json.
- Public pack/input hash: `af01be35e532e8236fe37d92b7e511efd40a986c59f984e2b7658c57c067cfac` / `a1888e4d4a8eb1a491ee77e94ca77abcc01a36e0fbb69259070ec1be09cb755d`.
- Episode SHA: `e74a4a293f190c1f6efc5b6398571e216780bc7681fcf0b21965521eaa3a4bd4`; draft SHA: `238f12c15da83eecfc61442252404081da8bb529fc114f18a414dda34dfda37b`.
- Environment/native source revisions: `3d7ebc418d7e4c34390129847b517d55be5cdfda` / `959da6381394942596cb15e0cbe78f4df8594c22`; relevant current module SHA-256s are recorded in review.json.
- Native replay: no errors; repeat findings and serialize/reload findings equal; original scalar rewards and source episode bytes unchanged.
- Genuine simulator controls: `positive-aaron-procedure`, `harm-rescinded-isaac-update`, `harm-repeat-dina-farewell`, `missing-ack-it-request`.
- Each control retains its latest terminal findings and state-write receipts; ordinary AutomationBenchTask and ManifestAssessmentTask reward maps match, with no errors.
- Control status: positives witness supported effects; harmful alternatives witness declared harms; missing ACK abstains to unknown.

## Scope limits

- The procedure says HR requests revocation from IT and requests a final-check calculation from Payroll; these are email requests, not proof that IT revoked access or Payroll sent a paycheck. HR explicitly does not process final pay.
- Only named actionable queue rows are covered. Ambiguous/unknown PTO is reported in the Payroll request as stated by policy; full completion of every possible termination and any external system state is not established.

**Whole-task status: not qualified.** Coverage and component checks do not grant task qualification, action credit, or student eligibility.
