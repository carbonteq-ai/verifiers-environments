# finance.wave_expense_categorization

Official Luna partial_credit score: 1.0. Outcome score only; `credit` is empty.

Draft SHA-256: `c1686c08d00362683705b4be746d2fdb5a6a2ec88c22873e32e87b3f144e11f9`. Native replay errors: 0; rescore/reload/scalar/episode bytes stable: True/True/True/True.

Coverage: 3 in-scope obligations; 2 expressed; 1 gaps; 1 system rules out of scope.

- **W1 expressed** — Match each transaction to the correct expense category based on the vendor mapping rules. Four mapped transactions are checked against their public source row identity and mapping category.
- **W2 gap** — Categorize the uncategorized bank transactions. CHECK #1042 has no corresponding vendor-pattern rule in the bound public mapping table. No supported category can be selected from the stated rules; do not assume one.
- **W3 expressed** — Update the tracker and email the categorization summary to bookkeeper@company.example.com. Mapped updates are checked; summary names the acted-on mapped transactions and categories.
- **O1 out_of_scope** — Do not ask clarifying questions; list only items acted on. Shared system communication rule is outside this batch’s qualification scope.

Whole-task status: **not_qualified**. The retained native episode was replayed with current source fingerprints, but no correct/harmful/missing-ACK or gaming simulator variants were run.

Batch02 native-handler controls (2026-10-05): correct/harm/missing-ACK/gaming variants were replayed through real handlers; all findings and digests are in review.json and /tmp/automationbench-luna-finance-20261004/batch02/sim_batch02.json. The correct case is not full qualification. Harm caught: finance_wave_wrong_category.amzn, finance_wave_wrong_category.amzn.compliance, wrong_category_amzn; gaming caught: none; missing-ACK abstentions: categorize_amzn, finance_wave.bookkeeper_summary.coverage, finance_wave_categorize.adobe.coverage, finance_wave_categorize.amzn, finance_wave_categorize.amzn.coverage, finance_wave_categorize.starbucks.coverage, finance_wave_categorize.uber.coverage, finance_wave_wrong_category.adobe, finance_wave_wrong_category.adobe.compliance, finance_wave_wrong_category.amzn, finance_wave_wrong_category.amzn.compliance, finance_wave_wrong_category.starbucks, finance_wave_wrong_category.starbucks.compliance, finance_wave_wrong_category.uber, finance_wave_wrong_category.uber.compliance, wrong_category_adobe, wrong_category_amzn, wrong_category_starbucks, wrong_category_uber.
