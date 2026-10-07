"""The public starting state as manifests read it.

Current AutomationBench task data nests some collections (Google Sheets rows
inside worksheets inside spreadsheets; Mailchimp subscribers inside
audiences), while the world the tools act on, and the reference episodes the
manifests were authored against, keep them as flat top-level lists. A nested
service is rebuilt through its schema and dumped with only explicitly set
fields, so no defaults or generated IDs are invented; services already stored
flat are returned unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from automationbench.schema.world import WorldState

_NESTED = {"google_sheets": ("spreadsheets", "worksheets"), "mailchimp": ("audiences", "subscribers")}


def public_initial_state(initial: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(initial)
    for service, (outer, inner) in _NESTED.items():
        value = initial.get(service)
        if isinstance(value, Mapping) and any(
            isinstance(item, Mapping) and inner in item for item in value.get(outer) or ()
        ):
            state[service] = WorldState.model_validate({service: value}).model_dump(
                mode="json", exclude_unset=True
            )[service]
    return state


__all__ = ["public_initial_state"]
