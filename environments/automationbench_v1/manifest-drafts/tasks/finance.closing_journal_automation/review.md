# finance.closing_journal_automation

Component-only assessment. The retained Luna score is evidence, not qualification. No action credit is declared.

Current draft SHA-256: `3f2fbb162390cb8b1e345a579969c716e6533e48f09886fa4fd19eee3d074e04`.
Coverage: 7 expressed, 1 gaps, 2 out of scope. Whole-task status remains not qualified.

Native retained-episode replay: native_episode_replay_complete; scalar rewards unchanged=True; source bytes unchanged=True; reload/rescore parity=True.

Genuine-handler controls: correct [closing-report=1.0, trial-balance-close-0=1.0, trial-balance-close-1=1.0, trial-balance-close-2=1.0, trial-balance-close-3=1.0, trial-balance-close-6=1.0, income-summary-close-line=1.0]; harm [closing-report=1.0, trial-balance-close-0=1.0, trial-balance-close-1=1.0, trial-balance-close-2=1.0, trial-balance-close-3=1.0, trial-balance-close-6=1.0, income-summary-close-line=0.0]; missing ACK [closing-report=unknown, trial-balance-close-0=unknown, trial-balance-close-1=unknown, trial-balance-close-2=unknown, trial-balance-close-3=unknown, trial-balance-close-6=unknown, income-summary-close-line=unknown]; duplicate final call [closing-report=1.0, trial-balance-close-0=1.0, trial-balance-close-1=1.0, trial-balance-close-2=1.0, trial-balance-close-3=1.0, trial-balance-close-6=1.0, income-summary-close-line=1.0].

These bounded controls do not grant whole-task qualification. Missing acknowledgements leave dependent evidence unknown; repeated calls grant no action credit.

Known limitations:
- Same-line checks require each nonzero revenue/expense account name, verbatim source amount and Income Summary, and the Income Summary / Retained Earnings / $47,500 close reference. They do not bind debit/credit roles to each distinct account on multi-sided prose lines or prove terminal account balances.
- Zero-balance and liability exclusion from journal entries are not expressed; the correct component control does not prove those exclusions.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.0; draft changed vs. last commit: True.
- Added harm zero-balance-account-in-closing-email (zero-balance Marketing Expense must not appear in the closing entries email, policy rule 5 and official body_not_contains Marketing). Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/7 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 7/7, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `44a46eecdca3fffa7ae079532ff9a9e3c0e666139020afee56f7d7ef2defe6a4`.
