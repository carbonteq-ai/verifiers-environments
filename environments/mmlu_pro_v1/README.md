# mmlu-pro-v1

CarbonTeq's standalone Verifiers v1 MMLU-Pro environment package.

This package loads `TIGER-Lab/MMLU-Pro` at Hub commit
`b189ec765aa7ed75c8acfea42df31fdae71f97be`, keeps the official category-specific
five-shot chain-of-thought prompt shape, and exposes deterministic answer
parsing plus `answer_parse_success` and `answer_correct` signals. The balanced
default selects 100 rows from each of the 14 categories (1,400 tasks). Set
`balanced=false` for the full 12,032-row test split.

The official evaluator uses a seeded random guess when answer extraction fails.
MMLU-Pro v1 intentionally scores an unparseable answer as zero and reports the
parse result separately; this is `mmlu-pro-cot-5shot-strict-v1`, not a claim of
bit-for-bit leaderboard equivalence. Reference prompt/parser source is pinned
to commit `f418b116db00b065c2aea046518d8fcf74d39872` of
[TIGER-AI-Lab/MMLU-Pro](https://github.com/TIGER-AI-Lab/MMLU-Pro/tree/f418b116db00b065c2aea046518d8fcf74d39872).

The package is independent of posttrain and the other environment packages.
