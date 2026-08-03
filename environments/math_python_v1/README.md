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
credentials. This is a local safety boundary; the release still requires the
immutable Docker image and lifecycle qualification described by the framework
plan, including success, error, timeout, cancellation, and process-exit cleanup.

The package remains independent of posttrain and the other environment packages.
