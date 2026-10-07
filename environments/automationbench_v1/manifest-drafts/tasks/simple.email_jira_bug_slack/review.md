# simple.email_jira_bug_slack — batch 13 review

Public replay: 954e77038e24c2ee27b8b0c11bd80332688666dc1f83883bf6036d1bcf782d08  
Draft: cd81b479436f1648c02d82cbae71bc02d43e1e4c68046c7dda53c300e5cbea38

Coverage: 2 expressed, 1 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-bug-email — Read the email
- **gap — goal:** create-jira-bug — The public initial state has no Jira project or issue inventory; `src/automationbench_v1/contracts/jira_effects.py` requires an admitted Jira issue collection and initial boundary for receipt-backed transitions, while `src/automationbench_v1/contracts/record_writes.py` does not admit Jira writes. The actual retained trace’s action log is not evidence of a durable issue. Need public project membership/identity plus receipt-backed created-and-retained issue evidence.
- **expressed — goal:** notify-engineering — notify the #engineering Slack channel

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
