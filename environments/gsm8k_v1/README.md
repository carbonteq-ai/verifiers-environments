# gsm8k-v1

CarbonTeq's standalone Verifiers v1 GSM8K environment package. It loads the
`openai/gsm8k` Hub dataset at an immutable Git revision and keeps that source
identity plus a canonical row SHA-256 in every `TaskData` record. The default
revision is `740312add88f781978c0658806c59bc2815b9866`, configuration `main`, and
split `test` (1,319 rows); `train` contains 7,473 rows at the same revision.

The task preserves the upstream Verifiers prompt and `####` final-answer
contract. The `correct` reward executes the bundled `verify.py` with
`math-verify` inside the Verifiers runtime, so the verifier dependency is not
added to the host evaluation environment. Invalid or unparseable predictions
score `0.0`; the task's `validate` hook checks that the gold answer scores `1.0`.

Direct declarative use:

```python
import verifiers.v1 as vf

config = vf.EnvConfig.model_validate(
    {
        "taskset": {
            "id": "gsm8k-v1",
            "dataset_repo": "openai/gsm8k",
            "dataset_revision": "740312add88f781978c0658806c59bc2815b9866",
            "dataset_config": "main",
            "split": "test",
        },
        "harness": {"id": "null", "runtime": {"type": "subprocess"}},
    }
)
environment = vf.Environment(config)
tasks = environment.taskset.select(1)
```

This project is independently installable and remains framework-neutral: it has
no dependency on posttrain, Trackio, W&B, TRL, vLLM, dstack, or the other
environment packages.
