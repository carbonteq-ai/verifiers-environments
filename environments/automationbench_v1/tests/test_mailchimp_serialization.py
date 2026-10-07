"""Declared set state must replay identically across process hash seeds."""

import json
import os
import subprocess
import sys
from pathlib import Path

from automationbench.schema.mailchimp import MailchimpSubscriber


def test_tag_set_serialization_is_stable_without_reordering_notes():
    contact = MailchimpSubscriber(
        id="contact",
        email="user@example.com",
        list_id="audience",
        tags={"registered", "attended", "VIP"},
        notes=["second", "first"],
    )
    serialized = contact.model_dump(mode="json")
    assert serialized["tags"] == ["VIP", "attended", "registered"]
    assert serialized["notes"] == ["second", "first"]
    assert contact.model_dump()["tags"] == {"registered", "attended", "VIP"}
    assert contact.to_display_dict()["tags"] == serialized["tags"]
    assert MailchimpSubscriber.model_validate(serialized) == contact


def test_retained_tag_order_canonicalizes_identically_across_hash_seeds():
    source_root = Path(__file__).parents[1] / "src"
    code = """
import json
from automationbench.schema.mailchimp import MailchimpSubscriber
data = dict(id="contact", email="user@example.com", list_id="audience",
            tags=["registered", "attended", "VIP"], notes=["second", "first"])
contact = MailchimpSubscriber.model_validate(data)
dump = contact.model_dump(mode="json")
print(json.dumps({"tags": dump["tags"], "notes": dump["notes"],
                  "display_tags": contact.to_display_dict()["tags"]}, sort_keys=True))
"""
    outputs = []
    for seed in ("1", "2", "37", "99"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(source_root)}
        outputs.append(subprocess.check_output([sys.executable, "-c", code], env=env, text=True))
    assert len(set(outputs)) == 1
    assert json.loads(outputs[0])["notes"] == ["second", "first"]
