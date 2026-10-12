"""Violation controls: re-execute Luna's tool calls (and mutated, violating variants) through the real simulator handlers,
wrap the captures in native envelopes (as tests/test_manifest_guard_assessments.native_fixture does, but with the task's real data),
score them with the repo draft, and report which goals pass and which guards fire.
Run from environments/automationbench_v1: .venv/bin/python shard3/guard-controls.py <M> <coverage.json> <out.json> [task ...]"""
import asyncio, copy, hashlib, importlib.util, json, re, sys
from pathlib import Path
from typing import Any, cast
sys.path.insert(0, "tests")
M = Path(sys.argv[1]); S = M / "shard3"
spec = importlib.util.spec_from_file_location("r", S / "shard3-replay.py"); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
import verifiers.v1 as vf
from verifiers.v1.mcp.execution import ToolServerReceipt
from verifiers.v1.trace import StateWriteReceipt, ToolServerExecutionEvent
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.loader import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_step_credit import manifest_outcomes
from automationbench_v1.taskset import AutomationBenchTask, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState, _registry

REG = _registry()
tasks16 = R.tasks_at(16)
calls = json.load(open(S / "luna-calls.json"))
READ = re.compile(r"(find|search|get|list|read|lookup|retrieve)", re.I)

def _pairs(old, new, key=""):
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k in new: yield from _pairs(old[k], new[k], k)
    elif isinstance(old, list) and isinstance(new, list):
        for a, b in zip(old, new): yield from _pairs(a, b, key)
    elif isinstance(old, (str, int)) and isinstance(new, (str, int)) and old != new and re.search(r"(id|url|uuid)$", str(key), re.I):
        yield str(old), str(new)

def run_ops(initial, ops):
    """Execute through the real handlers (as tests/test_notification_evidence.run_operations does) but record the arguments actually used:
    ids/urls minted by earlier calls are mapped from Luna's recorded results to the fresh ones before each call."""
    import test_notification_evidence as tne
    world = tne.WorldState.model_validate(copy.deepcopy(initial)); hydrated = world.model_dump(mode="json")
    idmap, events, writes = {}, [], []
    for index, o in enumerate(ops):
        raw = json.dumps(o["args"])
        for old, new in sorted(idmap.items(), key=lambda kv: -len(kv[0])): raw = raw.replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1])
        args = json.loads(raw)
        before = canonical_json(world.model_dump(mode="json"))
        result = REG.execute(o["tool"], raw, world=world)
        after = canonical_json(world.model_dump(mode="json"))
        if o.get("orig_result"):
            try:
                old_res = json.loads(o["orig_result"]); old_res = json.loads(old_res) if isinstance(old_res, str) else old_res
                for old, new in _pairs(old_res, json.loads(result)): idmap[old] = new
            except Exception: pass
        snapshots = {hashlib.sha256(v.encode()).hexdigest(): v for v in (before, after)}
        capture = tne.CapturedAction(occurrence_index=index, tool_name="execute_tool", arguments_json=canonical_json({"tool_name": o["tool"], "arguments": canonical_json(args)}),
            before_digest=hashlib.sha256(before.encode()).hexdigest(), after_digest=hashlib.sha256(after.encode()).hexdigest(), status="returned", result_json=canonical_json(result))
        invocation = f"execution-{index}"
        receipt = {"invocation_id": invocation, "phase": "returned", "state_read_revision": index, "state_write_revision": index + 1, "state_persistence": "applied", "state_conflict": False,
                   "evidence_json": [canonical_json({"kind": "automationbench_raw_action", "action": capture.model_dump(mode="json"), "snapshots": snapshots})]}
        events.append({"source": "tool_server", "receipt_json": canonical_json(receipt)})
        writes.append({"write_id": invocation, "expected_revision": index, "applied_revision": index + 1, "conflict": False})
    return {"tool_execution_events": events, "state_write_receipts": writes, "task_evidence": {"initial": hydrated, "final": world.model_dump(mode="json"), "complete": True}}

def native_trace(data, material):
    events, writes = [], []
    for index, reduced in enumerate(material["tool_execution_events"]):
        receipt = json.loads(reduced["receipt_json"]); payload = json.loads(receipt["evidence_json"][0]); action = payload["action"]
        identity = {"invocation_id": receipt["invocation_id"], "tool_name": action["tool_name"],
                    "arguments_json": canonical_json({"args": [], "kwargs": json.loads(action["arguments_json"])}), "state_read_revision": index}
        dispatch = ToolServerReceipt(**identity, event_index=0, phase="dispatch")
        returned = ToolServerReceipt(**identity, event_index=1, phase="returned", evidence_json=tuple(receipt["evidence_json"]), result_json=action["result_json"],
                                     state_write_revision=index + 1, state_conflict=False, state_persistence="applied")
        for envelope, revision in ((dispatch, index), (returned, index + 1)):
            events.append(ToolServerExecutionEvent(invocation_id=envelope.invocation_id, event_index=envelope.event_index, phase=envelope.phase,
                          receipt_seq=len(events), state_revision=revision, receipt_json=canonical_json(envelope.model_dump(mode="json"))))
        writes.append(StateWriteReceipt(write_id=returned.invocation_id, body_digest=hashlib.sha256(payload["snapshots"][action["after_digest"]].encode()).hexdigest(),
                                        expected_revision=index, applied_revision=index + 1, conflict=False))
    trace = vf.Trace(episode_id="guard-control", agent=vf.AgentInfo(config=vf.AgentConfig()), task=vf.TraceTask(type="Task", data=data),
                     tool_execution_events=tuple(events), state_write_receipts=tuple(writes), tool_state_revision=len(material["tool_execution_events"]),
                     is_completed=True, ok=True, info={"automationbench": {"end_state": material["task_evidence"]["final"]}})
    episode = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]})
    retained = cast(Any, episode.traces[0])
    retained.state = AutomationBenchState(world=material["task_evidence"]["final"], initial_state=data.initial_state, assertions=data.assertions)
    config = AutomationBenchTaskConfig(capture_actions=True)
    asyncio.run(AutomationBenchTask(data, config).score(retained))
    return ManifestAssessmentTask(data, config), retained

def score(t, contract, ops, patch=None):
    data = tasks16[t].data; init = copy.deepcopy(data.initial_state)
    if patch: patch(init)
    material = run_ops(init, ops)
    task, trace = native_trace(data, material)
    manifest_assessments.load_task_contract = lambda _n: contract
    try: asyncio.run(task.score(trace))
    finally: manifest_assessments.load_task_contract = R.packaged_loader
    _, required, harms = manifest_outcomes(trace); passed, undecided = R.goal_statuses(trace, contract)
    notes = [(f["check_id"], f["status"], f.get("value"), f.get("reason")) for f in R._latest_payloads(trace, R.OBLIGATION_OUTPUT) if f.get("kind") == "finding" and (f.get("status") != "valid" or f.get("value") != 1)]
    if notes and __import__("os").environ.get("GC_DEBUG"):
        for f in R._latest_payloads(trace, R.OBLIGATION_OUTPUT): print("DEBUG", json.dumps({k: v for k, v in f.items() if "digest" not in k and k != "instance_key"})[:1200])
        for e in (material["tool_execution_events"]): print("DEBUGEV", json.loads(e["receipt_json"])["evidence_json"][0][:900])
    return {"unmet": notes, "passed": passed, "required": required, "undecided": undecided, "harms": sorted({h[0] for h in harms}), "errors": len(trace.assessment_errors or ()) + len(trace.credit_errors or ())}

# ---- mutations ---------------------------------------------------------------------------------------------
def is_write(o): return not READ.search(o["tool"])
def leaves(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items(): yield from leaves(v, path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from leaves(v, path + (i,))
    else: yield path, x
def setp(d, path, v):
    d = copy.deepcopy(d); cur = d
    for p in path[:-1]: cur = cur[p]
    cur[path[-1]] = v; return d
def siblings(initial, value):
    """same-field values of the other records in any initial-state list holding a record with a field equal to value"""
    found = []
    def walk(x):
        if isinstance(x, list):
            recs = [e for e in x if isinstance(e, dict)]
            for e in recs:
                for k, v in e.items():
                    if v == value and isinstance(v, str) and len(recs) > 1: found.extend(o[k] for o in recs if o is not e and isinstance(o.get(k), str) and o[k] != value)
            for e in x: walk(e)
        elif isinstance(x, dict):
            for v in x.values(): walk(v)
    walk(initial); return found

def mutate_arg(ops, keys, newvalue_fn):
    """variants where a write op's argument (outer 'arguments' key in `keys`) is replaced"""
    out = []
    for i, o in enumerate(ops):
        if not is_write(o): continue
        for path, v in leaves(o["args"]):
            name = next((str(p) for p in reversed(path) if not isinstance(p, int)), "")
            if path and name.lower() in keys and isinstance(v, str):
                nv = newvalue_fn(v); patch = None
                if isinstance(nv, tuple): nv, patch = nv
                if nv is not None and nv != v: out.append((f"op{i}:{'.'.join(map(str, path))}", ops[:i] + [{**o, "args": setp(o["args"], path, nv)}] + ops[i + 1:], patch))
    return out
def duplicate(ops):
    return [(f"dup-op{i}", ops + [ops[i]], None) for i, o in enumerate(ops) if is_write(o)]
def append(ops, tool, args, patch=None): return [(f"append-{tool}", ops + [{"tool": tool, "args": args}], patch)]
def clone_sibling(init, value):
    """add a copy of the record holding a field equal to value (new value value+'9') so a wrong-record write is executable"""
    done = []
    def walk(x):
        if isinstance(x, list):
            for e in list(x):
                if isinstance(e, dict) and not done:
                    for k, v in e.items():
                        if v == value and isinstance(v, str):
                            c = copy.deepcopy(e); c[k] = value + "9"
                            if "id" in c and k != "id": c["id"] = str(c["id"]) + "9"
                            x.append(c); done.append(value + "9"); return
            for e in x: walk(e)
        elif isinstance(x, dict):
            for v in x.values(): walk(v)
    walk(init); return done[0] if done else None
def seed_channel(init):
    sl = init.setdefault("slack", {}); sl.setdefault("channels", [])
    if not sl["channels"]: sl["channels"].append({"id": "CGEN900", "name": "general", "member_ids": []})
def seed_user(init):
    sl = init.setdefault("slack", {}); sl.setdefault("users", [])
    if not sl["users"]: sl["users"].append({"id": "U900", "name": "pat", "real_name": "Pat Doe", "email": "pat@company.example.com"})

def variants(gid, ops, data):
    init = data.initial_state; other = "other.person@example.com"
    if gid.startswith("duplicate"): return duplicate(ops)
    if gid == "wrong-record-updated":
        def sib(v):
            s = siblings(init, v)
            if s: return s[0]
            probe = copy.deepcopy(init); nv = clone_sibling(probe, v)
            return (nv, lambda w, v=v: clone_sibling(w, v)) if nv else None
        return mutate_arg(ops, {"recordid", "record_id", "id", "contact", "deal", "contact_id", "deal_id", "objectid"}, sib)
    if gid in ("wrong-channel", "unrequested-channel-post-swap"):
        chans = [c for c in (init.get("slack") or {}).get("channels", [])]
        def swap(v):
            for c in chans:
                if v in (c.get("id"), c.get("name"), "#" + str(c.get("name"))):
                    o = next((d for d in chans if d is not c), None)
                    if o is None:
                        nv = "#zz-other" if v.startswith("#") else "CZZOTHER"
                        return nv, (lambda w: w.setdefault("slack", {}).setdefault("channels", []).append({"id": "CZZOTHER", "name": "zz-other", "member_ids": []}))
                    return ("#" + o["name"]) if v.startswith("#") else (o["id"] if v == c.get("id") else o["name"])
            return None
        return mutate_arg(ops, {"channel", "channel_id", "channel_name"}, swap)
    if gid == "unrequested-dm":
        users = (init.get("slack") or {}).get("users", [])
        return append(ops, "slack_send_direct_message", {"user": (users[0]["id"] if users else "U900"), "text": "FYI"}, None if users else seed_user)
    if gid == "unrequested-channel-post":
        chans = (init.get("slack") or {}).get("channels", [])
        return append(ops, "slack_send_channel_message", {"channel": ("#" + chans[0]["name"]) if chans else "#general", "text": "status update"}, None if chans else seed_channel)
    if gid == "unrequested-email": return append(ops, "gmail_send_email", {"to": other, "subject": "FYI", "body": "note"})
    if gid == "wrong-dm-recipient":
        users = (init.get("slack") or {}).get("users", [])
        def other_user(v):
            u = next((u for u in users if v not in (u.get("id"), u.get("name"), u.get("username")) and str(u.get("name", "")).lower() not in v.lower()), None)
            return None if u is None else (u["id"] if v in [x.get("id") for x in users] else u["name"])
        return mutate_arg(ops, {"user", "user_id"}, other_user)
    if gid in ("wrong-recipient", "wrong-invite-recipient"):
        out = mutate_arg(ops, {"to", "recipient", "email"}, lambda v: other if "@" in v else None)
        if not out:  # replies carry no explicit recipient: add one
            out = [(f"reply-op{i}:add-to", ops[:i] + [{**o, "args": {**o["args"], "to": other}}] + ops[i + 1:], None) for i, o in enumerate(ops) if o["tool"] == "gmail_reply_to_email"]
        return out
    if gid == "wrong-jira-project": return mutate_arg(ops, {"project", "project_key"}, lambda v: "OPS")
    if gid == "wrong-meeting-host": return mutate_arg(ops, {"host_email"}, lambda v: other)
    if gid == "wrong-calendar": return mutate_arg(ops, {"calendar", "calendarid", "calendar_id"}, lambda v: "cal_other")
    if "outside" in gid:  # trello card created outside the target list
        return mutate_arg(ops, {"list", "list_id"}, lambda v: (siblings(init, v) or ["lst_other"])[0])
    if gid == "ticket-created-with-wrong-policy-field": return mutate_arg(ops, {"priority"}, lambda v: "low")
    if gid == "subscription-reverted":
        subs = [o for o in ops if o["tool"] == "mailchimp_add_subscriber"]
        return append(ops, "mailchimp_archive_subscriber", {"list_id": subs[0]["args"]["list_id"], "email": subs[0]["args"]["email"]}) if subs else []
    if gid == "urgent-label-on-foreign-card":
        lab = [o for o in ops if o["tool"] == "trello_card_label"]
        return append(ops, "trello_card_label", {**lab[0]["args"], "card": "trello_foreign_card"}) if lab else []
    if gid == "other-subscription-created": return mutate_arg(ops, {"email", "email_address"}, lambda v: other)
    return []

def main():
    coverage = json.load(open(sys.argv[2])); only = sys.argv[4:]
    rows = []
    for t in [x["task"] for x in json.load(open(M / "shard3-tasks.json"))]:
        if only and t not in only: continue
        row = {"task": t}
        try:
            raw = json.load(open(f"manifest-drafts/tasks/{t}/draft.json")); contract = load_contract(json.dumps(raw).encode())
            ops = [{"tool": c["arguments"]["tool_name"], "args": json.loads(c["arguments"]["arguments"]), "orig_result": c.get("result")} for c in calls[t] if c["outer"] == "execute_tool"]
            data = tasks16[t].data
            row["luna_ops"] = [o["tool"] for o in ops]
            row["luna_reexecuted"] = score(t, contract, ops)
            writes = [o for o in ops if is_write(o)]
            row["omit_writes"] = score(t, contract, [o for o in ops if not is_write(o)]) if writes else None
            guards = [c.check_id for c in contract.checks if getattr(c, "role", None) == "harm"]
            row["guards"] = {}
            for gid in guards:
                vs = variants(gid, ops, data); res = []
                for label, vops, vpatch in vs:
                    r = score(t, contract, vops, vpatch); res.append({"variant": label, "ops_tail": [o["tool"] for o in vops][-2:], "fired": gid in r["harms"], "passed": r["passed"], "required": r["required"], "errors": r["errors"], "other_harms": [h for h in r["harms"] if h != gid]})
                row["guards"][gid] = {"variants": len(vs), "fires_in": [x["variant"] for x in res if x["fired"]], "silent_in": [x["variant"] for x in res if not x["fired"]], "detail": res}
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        rows.append(row); g = row.get("guards", {})
        print(t, row.get("error"), row.get("luna_reexecuted"), {k: (len(v["fires_in"]), v["variants"]) for k, v in g.items()}, flush=True)
    Path(sys.argv[3]).write_text(json.dumps(rows, indent=1) + "\n")
main()
