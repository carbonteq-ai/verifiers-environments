# support.zoho_desk_capacity_planning

Original Luna reference remains **official_partial** at 0.7222222222222222; preserve this partial result.

The manifest now checks all six roster members, including zero-ticket members, against their public `Max_Tickets` using finalized open-ticket records. It does not rank tickets or choose a preferred survivor.

Native replay loaded, scored, serialized/reloaded, and rescored with finding parity; public initial state matched; original score and episode bytes were unchanged. The new capacity finding and its scope both pass in that reference replay.

Real-handler controls moved either cap_t1/cap_t2 or cap_t4/cap_t5 and both valid alternatives passed all six agent rows. A one-move overloaded case failed only the over-capacity roster row. A missing acknowledgement still left final outcome facts checkable; no action credit is inferred.

Department weighted workload/report contents and preserving department assignment during redistribution remain gaps. There is no action-credit check; this component and reference replay do not qualify the whole task. Status: `not_qualified`.

Draft SHA-256: `cdac3da512ec0dd568094fbe01564aafab72c8eacd1c057e5f1c0aeb99e03598`. Control artifact: `/tmp/automationbench-luna-support-batch03-20261005/support.zoho_desk_capacity_planning.counts-controls.json`.
