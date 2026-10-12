"""Extract each shard-3 Luna episode's tool calls (outer execute_tool name/args) -> shard3/luna-calls.json"""
import json, sys
from pathlib import Path
import verifiers.v1 as vf
M = Path(sys.argv[1]); cov = {e["task_name"]: e for e in json.load(open(sys.argv[2]))["entries"]}
out = {}
for x in json.load(open(M / "shard3-tasks.json")):
    t = x["task"]; tr = vf.WireEpisode.model_validate_json(Path(cov[t]["source_episode_path"]).read_bytes()).traces[0]
    calls = []
    for ev in tr.tool_execution_events:
        d = ev.model_dump(mode="json"); r = json.loads(d["receipt_json"])
        if r.get("phase") != "returned": continue
        for e in r.get("evidence_json") or []:
            p = json.loads(e)
            if p.get("kind") == "automationbench_raw_action":
                a = p["action"]; calls.append({"outer": a["tool_name"], "arguments": json.loads(a["arguments_json"]), "status": a["status"], "result": a.get("result_json")})
    out[t] = calls
(M / "shard3" / "luna-calls.json").write_text(json.dumps(out, indent=1)); print({t: len(c) for t, c in list(out.items())[:5]})
