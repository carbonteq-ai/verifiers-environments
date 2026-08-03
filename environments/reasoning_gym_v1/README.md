# reasoning-gym-v1

CarbonTeq's standalone Verifiers v1 Reasoning Gym environment package.

The package pins Open-Thought Reasoning Gym at commit
`49b07130b3fcd12f2d064bba7c43869543a0e7e7` and delegates generation plus native
answer scoring to its registry. The default balanced selection cycles through
ten declared generators: `leg_counting`, `products`, `letter_counting`,
`number_sorting`, `knights_knaves`, `syllogism`, `shortest_path`, `graph_color`,
`countdown`, and `zebra_puzzles`. Train and evaluation use disjoint seed
namespaces, and each task records its generator, seed, source commit, and row
digest in `TaskData`.

The wheel vendors the pinned `reasoning_gym` source at that commit. This keeps
the v1 package independently installable and gives posttrain job packaging a
portable, hash-locked dependency closure instead of a nested VCS requirement.

This implementation is ready for package-level deterministic qualification; it
is not yet a model baseline or framework catalog release. The package remains
independent of posttrain and the other environment packages.
