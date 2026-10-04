"""Bind manifest working inputs to the native executor's retrospective source."""

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass

from .capture import canonical_json


@dataclass(frozen=True)
class AdmittedManifestInput:
    """Immutable validated wire bytes; decode a fresh copy only when needed."""

    source_json: str
    input_json: str

    def decode(self):
        return json.loads(self.input_json)


def admit_manifest_source(task, request, context):
    """Recheck the raw source before any cached evidence or result is admitted.

    Views remain freely prepared working material. They cannot substitute their
    own trace for the sealed source supplied by the native executor. Direct
    assessor calls without that executor anchor deliberately fail unavailable.
    """
    if len(request.views) != 1 or context.views != request.views:
        raise ValueError("manifest_source_view_shape_invalid")
    sealed = context.retrospective_source()
    if sealed.identity != request.source or request.run.snapshot_id != sealed.snapshot_id:
        raise ValueError("manifest_executor_source_identity_mismatch")
    view = request.views[0]
    if view.input_json is None:
        raise ValueError("manifest_source_inline_input_required")
    key = (sealed.snapshot_id, sealed.source_digest, view.view_id, view.input_digest)
    cache = task.__dict__.setdefault("_manifest_source_admission_cache", OrderedDict())
    if key in cache:
        admitted = cache[key]
        if admitted.source_json != sealed.source_json or admitted.input_json != view.input_json:
            raise ValueError("manifest_source_admission_cache_wire_mismatch")
        return admitted
    raw = json.loads(sealed.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    material = context.input(view.view_id)
    text = canonical_json(material)
    if hashlib.sha256(text.encode()).hexdigest() != view.input_digest:
        raise ValueError("manifest_source_view_digest_mismatch")
    if canonical_json(material["source"]) != canonical_json(safe):
        raise ValueError("manifest_view_executor_source_mismatch")
    admitted = AdmittedManifestInput(sealed.source_json, view.input_json)
    cache[key] = admitted
    while len(cache) > 4:
        cache.popitem(last=False)
    return admitted
