# simple.hs_update_contact_tag

Public-input contract only; historical score and misses are preserved. This draft does not grant qualification or action credit.

- Original retained score: 1.000 (recorded_full_score; official_full).
- Public pack SHA: `351938e9a861047b71d6b1f4eec63ddd9b5772bd586d6edaf4b5d0699dd2c379`; input SHA: `3db20e6d01e83df150c3b911f106ae43cbdd2b0c5f5639851cff004d340e0ee8`.
- Draft SHA: `96551d1c7c3063a27d3b7b2fcba04ddcbefbef527dcd79c282f2dd01c37a04f2`; 1 public obligations expressed; 2 checks; outcome-only.
- Native replay: errors=0; scalar/rescore/reload/source-bytes/public bindings all `True`.
- Synthetic controls: three actual-handler cases (correct/adverse/missing ACK), ordinary/manifest scalar equality and reload parity verified: `True`.
- Full raw controls and source fingerprints: `/tmp/automationbench-luna-simple-batch17-20261005/controls_full_v1.json`.
- Findings treat scope/completeness separately from goal values; a valid terminal outcome can coexist with missing ACK and abstained action evidence.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; the counted goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0).

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Notes: Inert goal requested_target_retained_with_field_and_profile_preserved (records.retained_when) is not read by step credit; the counted effects goal (hs_004 hs_tag=enterprise) carries the requirement. The 'profile preserved' half cannot be expressed as a counted kind here. No wrong-contact guard: the state holds a single contact and a call for another id errors without any state change (record_writes is a state diff), so such a guard could never fire.

Gaps: Profile-preserved check (inert).
