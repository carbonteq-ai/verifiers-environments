"""A task rebuilt from (data, config) runs as the class the taskset loads for that row."""

from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTask,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)


def test_env_server_rebuild_keeps_the_manifest_task_class():
    config = AutomationBenchConfig(domains=["finance"], task_names=["finance.escrow_tracking"],
                                   task={"manifest_assessments": True, "capture_actions": True})
    (loaded,) = AutomationBenchTaskset(config).load()
    assert type(loaded) is ManifestAssessmentTask
    # Verifiers' env server: task_cls(data_cls.model_validate(data), config_type().model_validate(config))
    data = type(loaded.data).model_validate(loaded.data.model_dump(mode="json"))
    task_config = AutomationBenchTaskConfig.model_validate(loaded.config.model_dump(mode="json"))
    rebuilt = AutomationBenchTask(data, task_config)
    assert type(rebuilt) is ManifestAssessmentTask
    assert rebuilt.data == loaded.data


def test_rebuild_without_manifest_selection_stays_the_base_class():
    config = AutomationBenchConfig(domains=["finance"], task_names=["finance.escrow_tracking"])
    (loaded,) = AutomationBenchTaskset(config).load()
    assert type(loaded) is AutomationBenchTask
    assert type(AutomationBenchTask(loaded.data, loaded.config)) is AutomationBenchTask
