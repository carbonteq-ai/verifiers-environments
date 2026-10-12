# simple.sf_create_case — Simple batch 19

**Status: not qualified.** This manifest covers selected public outcome components; the recorded reference score is preserved without promoting it to eligibility or qualification.

## Covered public obligations

- `requested_salesforce_case_created`: Requires one new case on the source-bound account with the requested subject, priority and status.

## Validation

- Current draft SHA: `47f0beb56df923a507e7c8c20b50b8163ae7085103c37ea7078e806b3598adf2`. Native replay used the exact public prompt/initial/tool allowlist and source episode `e4228041c424f71911255f6e402f27377231b7da514c1cdf17a6306cae0d5af3`.
- 3 completed genuine-handler controls: correct, wrong-goal, missing write ACK.
 - Ordinary benchmark scalar, native findings and rewards remained equal after serialization/reload. No trace, assessment or credit errors were present. Raw arguments, results, ACK state, native episode and per-run source fingerprints are linked in `review.json`.

## Limits

- No action or token credit is declared. Shared narration policies remain out of scope. Wrong-goal controls do not claim harm absent public prohibition.

## Re-review (shard 3)

Supersedes the earlier statement that no harm guard is asserted: guards are duplicate-case, case-for-wrong-account. Goals re-derived from the prompt and task data. Luna replay: 1/1 required goals met, 0 harms. No-op control (prompt, no tool calls): 0 goals met, 0 harms. Verdict: eval-ready.

Edit: Added case-for-wrong-account harm guard.
