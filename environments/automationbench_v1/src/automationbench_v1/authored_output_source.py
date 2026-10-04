"""Select raw authored-output material from a native trace, without a verdict."""

import base64
import copy
import hashlib


def build_authored_output_material(trace):
    """Keep exact SDK bytes and native generated-node inventory for rederivation.

    Artifact restoration is the replay caller's responsibility. This builder
    does not guess filesystem paths or fall back to the last root reply.
    """
    sdk_info = trace.info.get("codex_sdk")
    artifacts = trace.state.artifacts
    sdk_raw = artifacts.get("codex_sdk/events.json")
    harness = getattr(trace.agent.config, "harness", None)
    return {
        "schema_version": 1,
        "trace_id": trace.id,
        "complete": trace.is_completed and trace.ok and not trace.errors,
        "sdk_declared": (
            sdk_info is not None or "codex_sdk/events.json" in artifacts
            or getattr(harness, "id", None) == "codex_sdk"
        ),
        "sdk_info": copy.deepcopy(sdk_info),
        "sdk_artifact_base64": base64.b64encode(sdk_raw).decode("ascii") if type(sdk_raw) is bytes else None,
        "sdk_artifact_sha256": hashlib.sha256(sdk_raw).hexdigest() if type(sdk_raw) is bytes else None,
        "native_nodes": [
            {
                "node": index, "parent": node.parent, "sampled": node.sampled,
                **node.message.model_dump(mode="json", include={"role", "content"}),
            }
            for index, node in enumerate(trace.nodes)
        ],
        "native_calls": [
            {"node": call.node, "finish_reason": call.finish_reason, "failed": call.error is not None}
            for call in trace.calls
        ],
    }
