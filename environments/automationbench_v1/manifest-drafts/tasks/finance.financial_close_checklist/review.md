# finance.financial_close_checklist

Status: **not qualified**. Expressed 1 checks, with 1 explicit gaps. Delivery and any listed exclusion guards do not verify task calculations, content, or other state changes.

Luna replay: [{'check_id': 'recipient_0_delivered', 'candidate': ['public.request@1', '587064875a05005057cfe2a8641045cfa598c8dd3510ad2322b7959a5a3d3075', 'authored', 'finance.financial_close_checklist-recipient-0'], 'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect'}, {'signal': 'finance_financial_close_checklist.recipient_0', 'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect'}, {'signal': 'finance_financial_close_checklist.recipient_0.coverage', 'status': 'valid', 'value': 1.0, 'reason': 'obligation_scope_closed'}]; errors=[]; rescore/reload=True/True; scalar/bytes unchanged=True/True.

Simulator variants (correct, wrong route, missing ACK) were run through native scoring. Excluded-entity attack: None.

Batch01 native-simulator audit (2026-10-05): real AutomationBench native-handler component variants are retained (genuine_simulator_correct, genuine_simulator_wrong_route_or_recipient, genuine_simulator_missing_ack, excluded_entity_attack). They are not whole-task qualification. Current draft SHA-256: `97a474121b8d99c01ec672dec2444cab6ec1531148889e2e8f89928cb8378d2f`. See review.json for the underlying results and interpretation.
