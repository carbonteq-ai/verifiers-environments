# hr.equipment_provisioning - round 6 draft (hr-b)

Public pack batch-06 #7; Luna episode 1e6efc27...245422b. Status: **qualified_candidate**, blocked on a task-data repair (D2).

## Coverage
14 obligations: 10 in scope, all expressed; 0 gaps; 4 out of scope (2 system rules, home address, the already-shipped hire).
Eligible hires are full-time, start next week and have empty Notes: Ada, Brian, David, Greta, Hugo.
- Ticket checks: name, department laptop (rival model excluded), keyboard/mouse/headset, monitor only for remote hires.
- IT list (it-ops@ email or #it-general): delivered; per hire, the laptop and monitor rule on one line; peripherals named.
- Guards: no ticket/order naming a contractor (Jira, Gmail, Slack); no duplicate ticket per hire.

## Luna replay
Every goal is 1 and both guards are 0; no errors. Contractor-guard compliance abstains because of the Slack scope defect (D1).
Rescore and reload repeat; the scalar reward and the episode bytes are unchanged.

## Simulator (Jira project IT seeded by the harness)
- Correct runs (Gmail list or Slack list) score 1 everywhere.
- Harmful run: duplicate, wrong laptop, office monitor, hedged models and contractor tickets each caught.
- The shotgun IT list and the wrong-recipient run are unknown until D1 is fixed. With Slack users seeded, they score 0.
- Missing ACK abstains.

## Decisions
- Elena Rossi (already shipped) is neither required nor penalized.
- IT means it-ops@company.example.com or #it-general.
- An office ticket that says "no monitor" fails. This false negative is accepted to stop monitor shotgunning.

## Defects
- D1: Slack scope needs a `users` collection that the public state lacks, so Slack zeros stay unknown.
- D2: the task declares no Jira project, so current validation makes the required tickets impossible to create.

## Coordinator note (2026-10-04): Jira project

Defect D2 is fixed in the AutomationBench fork and the vendored copy. The task declares project `{id: it, key: IT, name: IT Operations}` and now offers `jira_project`. Lookup is exact first, otherwise a unique case-insensitive whole-word match, so "IT" or "operations" both find it. Creation still requires an exact key. Simulator runs that added an "IT" project by hand now match the shipped task data.
