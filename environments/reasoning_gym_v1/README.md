# reasoning-gym-v1

CarbonTeq's standalone Verifiers v1 Reasoning Gym environment package.

The package pins Open-Thought Reasoning Gym at commit
`49b07130b3fcd12f2d064bba7c43869543a0e7e7` and delegates generation plus native
answer scoring to its registry. The default balanced selection cycles through
ten declared generators: `leg_counting`, `products`, `letter_counting`,
`number_sorting`, `knights_knaves`, `syllogism`, `shortest_path`, `graph_color`,
`countdown`, and `zebra_puzzles`. Train and evaluation use disjoint seed
namespaces, and each task records its generator, seed, source commit, and row
digest in `TaskData`. Every task also carries a bounded-reasoning system prompt:
follow the generator's requested answer format, verify a candidate at most
once, stop when the answer is known, and never repeat a completed derivation.
This keeps long-thinking policies from turning simple procedural tasks into
length-truncated, untrainable rollouts without changing native scoring.

Scoring always gives the selected generator's native verifier first authority.
Generators such as `graph_color` keep a structured oracle in task metadata
rather than a textual `answer`; for those tasks the cascade returns the native
score and does not apply string, numeric, or symbolic fallback matchers. This
preserves valid JSON-solution tasks without inventing a string oracle.

Binary syllogisms use a strict terminal-decision verifier. Reasoning may precede
the answer, but the response must end in one unambiguous `Yes` or `No`; merely
mentioning an oracle label no longer earns length-dependent partial credit.

Online-RL curricula can select `reward_mode: boxed_exact`. In that mode the
task prompt requires one final `\\boxed{...}` answer, only the box is passed to
the generator's native verifier, and native partial scores are reduced to an
exact `0` or `1`. This prevents explanation length and incidental oracle text
from becoming reward components while preserving each generator's verifier.

The wheel vendors the pinned `reasoning_gym` source at that commit. This keeps
the v1 package independently installable and gives posttrain job packaging a
portable, hash-locked dependency closure instead of a nested VCS requirement.

This implementation is ready for package-level deterministic qualification; it
is not yet a model baseline or framework catalog release. The package remains
independent of posttrain and the other environment packages.
