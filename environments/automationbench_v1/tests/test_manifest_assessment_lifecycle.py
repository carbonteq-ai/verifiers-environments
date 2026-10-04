"""A failed current assessor never authorizes its earlier partial output."""

import pytest
from test_manifest_guard_assessments import RAW_SIGNAL, penalties, run_guard

from automationbench_v1.manifest_assessments import ManifestAssessmentTask


@pytest.mark.parametrize("status", ["failed", "interrupted"])
def test_partial_then_failed_same_run_produces_no_credit(monkeypatch, status):
    original = ManifestAssessmentTask.plan_credit
    checked = []

    def changed(self, source, batches, context):
        complete = [batch for batch in batches if batch.run.status == "complete"]
        finding = next(batch for batch in complete
                       if batch.assessments[0].signal.signal_id == RAW_SIGNAL)
        partial = finding.model_copy(update={"run": finding.run.model_copy(update={"status": "partial"})})
        failed = finding.model_copy(update={
            # Native failure retains findings already published by the run.
            # Dropping them would be a history rewrite, not a valid failure.
            "run": finding.run.model_copy(update={"status": status}),
        })
        selected = [batch for batch in complete if batch is not finding]
        requests = original(self, source, (*selected, partial, failed), context)
        assert requests == []
        checked.append(True)
        return requests

    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", changed)
    _, _, trace = run_guard(monkeypatch)
    assert checked and not penalties(trace)
