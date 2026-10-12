"""Apply the v2 acceptance rule to replay-rows.json -> gates.json (run from anywhere)."""
import json,sys
M=sys.argv[1]
rows=json.load(open(M+'/shard3/replay-rows.json'))
tasks={x['task']:x for x in json.load(open(M+'/shard3-tasks.json'))}
out={}
for r in rows:
    t=tasks[r['task']];reasons=[]
    full=r.get('luna_class')=='official_full'
    if 'error' in r: reasons.append('error:'+r['error'])
    else:
        if r['binding_16'] is not None: reasons.append('binding:'+str(r['binding_16']))
        if r['assessment_errors'] or r['credit_errors']: reasons.append('errors')
        if r['required']==0: reasons.append('no_required_goals')
        elif r['undecided']: reasons.append('undecided_goals')
        if full and r['passed']!=r['required']: reasons.append('goals_not_all_met_on_full_pass')
        if full and r['harms']: reasons.append('harm_on_full_pass')
        if not full and (r.get('luna_class')!='official_partial' or (r.get('luna_score') or 0)<.5): reasons.append('luna_not_solved')
    out[r['task']]=dict(task=r['task'],luna_partial_credit=t['luna_partial_credit'],draft_status=t['draft_status'],
      loads='error' not in r,binds=r.get('binding_16') is None and 'error' not in r,
      replay_ok=('error' not in r) and not (r.get('assessment_errors') or r.get('credit_errors')),
      required_goals_decided=(r.get('required',0)-r.get('undecided',0)) if 'error' not in r else 0,
      required_goals_met_on_luna=r.get('passed'),harms_on_luna=r.get('harms'),rebound=r.get('rebound',False),
      accepted=not reasons,reject_reasons=reasons)
json.dump(out,open(M+'/shard3/gates.json','w'),indent=1)
print(sum(v['accepted'] for v in out.values()))
