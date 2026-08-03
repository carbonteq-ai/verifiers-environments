# math-python-v1

CarbonTeq's standalone Verifiers v1 Math Python environment package.

The taskset loads `DigitalLearningGmbH/MATH-lighteval` at immutable revision
`0530c78699ea5e8eb5530600900e1f328b48acad`, extracts the final boxed answer,
and records the problem level, type, source revision, and row digest. Rewards
use Verifiers' `math-verify` boxed-answer checker and expose parse-success and
symbolic-correctness metrics.

Tasks expose a bounded, task-scoped Python MCP tool. Each cell is replayed in a
fresh child interpreter with bounded time/output, accepted-cell state isolated
through the Verifiers state channel, and a minimal environment without
credentials. The test binding can deterministically round-robin rows by problem
type with `order_seed` and `balance_by_type`; the train binding keeps the same
source semantics but uses a stochastic host sampling policy. The image recipe
is `images/math-python/Containerfile`; the release still requires publishing
that image by digest and completing success, error, timeout, cancellation, and
process-exit cleanup qualification described by the framework plan.

The package image is published in the CarbonTeq OCI registry at
`registry.lan/carbonteq/math-python-v1@sha256:67624f5e71f8a5c89d25bc6c42370eb6e71b8569788aa818e5d3fe8585f15f15`.
Use this digest, not the publication tag, when an image reference is required.
The image publication does not remove the remaining success, error, timeout,
cancellation, and process-exit lifecycle qualification requirement.

The package remains independent of posttrain and the other environment packages.
