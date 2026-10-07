# operations.chatgpt_feedback_analysis: round-4 review

Public pack `batch-11.json` task 1. Luna episode sha256 `499275a1…f19e`. Whole task: **qualified candidate** (needs independent review).

**Coverage.** 15 obligations reviewed: 7 in scope, 8 out of scope (6 need sentiment judgement, 2 are system-prompt rules). Round 3: 4 expressed. Round 4: **7 expressed, 0 gaps.** Draft: 8 checks, outcome only.

**What changed (mechanism 9: guards over the Gmail population).** Each guard decides per bound message at scoring time.
- **Seasonal:** an in-scope email whose body has winter, summer, seasonal or resort. This replaces the table-anchored guard. The domain-substring half of the rule is not expressible but adds no email here.
- **Self-resolved:** an in-scope email whose body has a listed phrase ("resolved", "fixed", "no action needed", "issue has been addressed"). Only fb_010 matches.
- **Skipped emails (posted / marked read / analysed in ChatGPT):** Feedback emails out of scope, meaning PROCESSED fb_008, internal fb_006, or before 2026-01-29 fb_007.
- **Wins post without the customer email:** a #customer-wins post that names an in-scope email by subject or body but lacks its sender address verbatim.

**How a post is tied to an email.** A post refers to an email if it contains the sender verbatim, the whole subject, or the whole body verbatim.
- If it names only other Feedback emails, it is not about this email.
- If it names no Feedback email, the result is unknown.
- The first build left bodies out of this "names none" test, so a quoted body made unrelated emails unknown. That was fixed and every chatgpt run was repeated.

**Luna replay** (final draft, updated engine). Scalars (0.818) and bytes are unchanged, and rescore and reload repeat. All scopes are closed and every guard finds 0 violations. Mark-read scores 1 for all 10. The ChatGPT analysis check is 0 for all 10 because Luna never called ChatGPT; this is a real counterexample.

**Genuine-simulator alternatives** (22 runs on the final draft; 3 repeated on rescore and reload on the updated engine):
- **Correct runs:** the full path and one batched ChatGPT prompt pass with no guard firing.
- **Each harm fires its guard once:**; the seasonal email posted, by sender or by subject; the self-resolved email posted, by sender or quoting its body; internal and old emails posted; PROCESSED and internal emails marked read; a skipped email sent to ChatGPT; a wins post with no email; a wins post with the email in a changed case.
- **Game attempts stay unknown, never compliant:** a paraphrased self-resolved post, and a wins post naming nothing.
- **Missing pieces score 0 per email.**
- **Missing acknowledgement:** the affected checks abstain.

**Defect found (R4-D1, performance).** Guard scoring re-digests the full source once per instance. On the old engine one Luna scoring took about 45 minutes. Reproducer: `scratchpad/round-4/operations/defect_guard_digest_perf.py`.
