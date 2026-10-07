# finance.qb_undeposited_funds

Recorded official scalar: `0.0`. This retained reference remains partial; these message components do not qualify the whole task or establish that deposits were created.

## Current validation

- Draft SHA-256 at replay and controls: `b4d29aa17559156fc9e1f9335ba2a76d7b944bff7ab696501bb68cca859a614b`. Source episode SHA-256: `11edf129d8305ba2dab35c591355fe36a28ff15f58abe8228d4103fb34e7a541`. Source episode bytes remained unchanged.
- Native replay artifact: `/tmp/automationbench-luna-finance-20261005-batch08/deposit-provenance/native-replay.json` (SHA-256 `133b643d056fd805da8d4c1823f662bca27b2a6b3e511a8442aaa4d37e1a3bc8`). First score, same-trace rescore, and serialized/reloaded rescore all have empty trace, assessment, and credit error inventories. Scalars and logical findings are stable. The 10 native tool events and 5 ACKs in the recorded episode are recorded.
- Genuine-handler controls with full raw invocation arguments/results, ACK receipts, handler material, native episodes, and before/after source module fingerprints: `/tmp/automationbench-luna-finance-20261005-batch08/deposit-provenance/controls-full-evidence.json` (SHA-256 `c71d4fe34c4af4b81ce77e9722725ab905cc1bc900d8d24a99a3ce9ede7d013d`). All three cases bind the same draft/source hashes. Native source HEAD was `3d7ebc418d7e4c34390129847b517d55be5cdfda`; all 129 Python modules had aggregate hash `40167ca2572eab66e49d4874d0cd6e42aaefc863787bbb8da0e347726654baf9` both before and after each run. The empty changed-source map means no module bytes changed during a run; full module maps are in the artifact.
- Correct component control: checks valid=1, two ACKs, rewards both 1.0. Wrong credit-card total control: method component 1 and card component 0, two ACKs, ordinary and manifest rewards both 2/3. Missing policy-read ACK: both checks abstain (`obligation_effect_scope_unavailable`); send ACK remains present.
- The earlier compact controls did not contain raw handler/ACK receipts, and their replay changed-module map was incorrectly empty due to a path bug. They remain historical only; see the superseded validation-history entry in `review.json`.

## Public obligations and limits

- **deposit-creation — gap**: the public tool list has no create-deposit operation, and no deposits collection/handler is available. The task’s central persisted deposit action cannot be validated.
- **deposit-summary — expressed component**: email the controller a summary with relevant source amounts. The current checks cover bounded source-derived email components.
- **deposit-procedure — partial component**: the prompt/procedure conflicts on grouping by deposit date versus payment method. The checks follow the procedure’s method grouping. They do not establish persisted separate deposits, memo references, investigation status, or that the 30-day payment was not deposited.

See `review.json` for per-check anchors, artifact links, exact case results, source fingerprints, and retained history.
