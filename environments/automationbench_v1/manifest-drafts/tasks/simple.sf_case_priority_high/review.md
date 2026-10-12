# simple.sf_case_priority_high — Simple batch 19

**Status: not qualified.** This manifest covers selected public outcome components; the recorded reference score is preserved without promoting it to eligibility or qualification.

## Covered public obligations

- `target_case_updated`: Requires an acknowledged persisted update to the exact target case with priority High.

## Validation

- Current draft SHA: `a05ab07954262143ca16edcf514210cc160a6d1e71eeea030affff007d67542c`. Native replay used the exact public prompt/initial/tool allowlist and source episode `249015db21420e535f668c90c3181a9803e28b601f42b990b18ba15c63846296`.
- 3 completed genuine-handler controls: correct, wrong-goal, missing write ACK.
 - Ordinary benchmark scalar, native findings and rewards remained equal after serialization/reload. No trace, assessment or credit errors were present. Raw arguments, results, ACK state, native episode and per-run source fingerprints are linked in `review.json`.

## Limits

- No action or token credit is declared. Shared narration policies remain out of scope. Wrong-goal controls do not claim harm absent public prohibition.

## Re-review (shard 3)

Supersedes the earlier statement that no harm guard is asserted: guards are wrong-record-updated. Goals re-derived from the prompt and task data. Luna replay: 1/1 required goals met, 0 harms. No-op control (prompt, no tool calls): 0 goals met, 0 harms. Verdict: eval-ready.
