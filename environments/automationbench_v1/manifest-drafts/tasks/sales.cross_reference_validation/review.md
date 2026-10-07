# sales.cross_reference_validation (batch04)

The reference created the source-matching Quantum Labs opportunity (native create check=1) but did not read the Validation Rules or current VP email and did not leave the requested checklist note (check=0). Native controls show correct opportunity and note actions pass; a wrong amount and wrong note parent fail. The new draft no longer demands unsupported Opportunity.contact_id because the create handler cannot set it.

Original Luna score: 0.200000 (official_partial). Native replay found 16 findings, no errors; source bytes and scalar rewards were unchanged, serialized reload/rescore findings matched.

Coverage: 3 expressed components; 1 gaps; 2 out of scope. Whole-task status: **not qualified**.

Limitations: The exact create outcome and note content are expressible, but the manifest only requires the policy reads and exact target output; it does not verify that the chosen contact is active VP+, belongs to the account, and has no open opportunity under the current rules. The correct native control passes and a wrong amount or note parent fails. A missing ACK makes a requested create unknown; it is outcome evidence only, not action credit. Exact native reads of msg_val_003 pass, a different known policy message fails, and missing ACK abstains; this verifies the declared message-read component only.

Simulator controls: native read of Validation Rules: rules_read=1; native get of current VP policy message: exact msg_val_003 read=1; other known policy message=0; missing ACK abstains; create correct Quantum Labs opportunity and checklist note: both outcome checks=1; wrong opportunity amount: validated_opportunity_created=0; note attached to wrong contact: validation_audit_note_created=0; missing ACK on opportunity or note create: missing create abstains unknown; action credit is not declared.
