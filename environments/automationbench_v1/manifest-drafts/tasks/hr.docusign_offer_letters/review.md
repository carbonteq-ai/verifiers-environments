# hr.docusign_offer_letters — Luna manifest review

Whole task: **not_qualified** (2/4 in-scope obligations expressed; 2 gap(s)).

## Expressed checks (2)
- **unapproved-offer-blocked** (`unapproved-offer-blocked`): Guard blocks envelope creation for a pending/unapproved row; tested with native DocuSign handler.
- **approved-offers-sent** (`approved-offer-envelope`): Declared using task public rows and deterministic effect evidence.

## Gaps
- **offer-terms-correct** [generated_object_relationships]: The existing DocuSign record adapter exposes envelope lifecycle and signers but the contract has no stable task-independent path to the template merge-field set for comparing all source terms.
- **tracker-marked-after-send** [other:cross_service_ordered_status]: The current draft expresses the signed envelope effect but omits a complete status transition and created-envelope to tracker-row join; this gap is intentionally not credited.

## Luna replay
- `unapproved-offer-blocked`: valid=0.0 x3.
- `approved-offer-envelope`: valid=1.0 x2, inapplicable=None x1.
- Errors: 0; findings repeat/reload: True/True; scalar and episode bytes unchanged: True/True.

## Simulator and limits
- approved offers: Approved-row envelope effects scored 1.
- unapproved envelope: Unapproved-envelope guard fired and compliance scored 0.
- missing ACK: Send obligation abstained; no missing evidence was scored as a pass.
- duplicate envelope: Required-send goal remained satisfied; duplicate prevention is not expressed.
- Out of scope: system-no-clarifying-questions.
- Out of scope: system-list-only-acted-on.
- Source authority: public prompt and initial state; hidden assertions do not define requirements. Whole-task status remains not qualified while any in-scope obligation is a gap.
