# ifeval-v1

CarbonTeq's standalone Verifiers v1 IFEval environment package.

This package loads the 541 held-out IFEval prompts from `google/IFEval` at Hub
commit `966cd89545d6b6acfd7638bc708b98261ca58e84`. The source's physical split
is named `train`, but the package exposes it only as logical purpose
`evaluation`. All 25 instruction IDs present at that revision have typed,
deterministic checkers. Scoring emits strict/loose instruction and prompt
accuracy; the primary reward is `strict_prompt_accuracy` and no judge model or
network call is used during scoring.

The strict and loose transforms follow Google's Apache-2.0 reference evaluator
at commit `e6890f85757dd84e27ca6df2dd30651dafad28e0`; attribution is in
[`NOTICE`](NOTICE). The package is independent of posttrain and the other
environment packages.
