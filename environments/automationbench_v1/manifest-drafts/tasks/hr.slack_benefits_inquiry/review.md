# hr.slack_benefits_inquiry — component review

- Public batch: batch04 HR index 4; pack SHA-256 `29539f3639ae9402772aceaf1dddc62b3b571aba8976936e664d41ae7f48a902`.
- Draft SHA-256 `617f23d238910c66e5907ba75ae0663bfbf9fbd33337fbdeaf721c1409fdc156`; source episode SHA-256 `24d28caf15d43f6f52e84a32b1e107a08765d58b85e95017642e02c07063cb99`.
- Original recorded score retained: `{'partial_credit': {'score': 0.6, 'weight': 1.0}}`. This is partial reference evidence, not qualification.
- Coverage: 5 expressed, 0 gaps, 0 explicitly out of scope (5 reviewed). Gap categories: `{}`.
- Native replay: no errors; rescore/reload consolidated results repeated; original scalar and episode bytes unchanged. Reload batch partition differs.
- Genuine simulator controls: 2 executed; unavailable controls: 0.
  - `correct-current-answers`: hr.benefits_answer: status=valid value=1.0 reason=obligation_witnessed_required_effect; hr.benefits_answer.coverage: status=valid value=1.0 reason=obligation_scope_closed; hr.uncovered_benefit_forward: status=valid value=1.0 reason=obligation_witnessed_required_effect; hr.uncovered_benefit_forward.coverage: status=valid value=1.0 reason=obligation_scope_closed
  - `gaming-stale-faq`: hr.benefits_answer.coverage: status=valid value=1.0 reason=obligation_scope_closed; hr.uncovered_benefit_forward.coverage: status=valid value=1.0 reason=obligation_scope_closed

Whole-task status: **not qualified**. Source revisions: env HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, native HEAD `959da6381394942596cb15e0cbe78f4df8594c22`; see `review.json` for working-tree hashes.
