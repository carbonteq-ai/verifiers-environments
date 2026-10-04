"""Composite record identities for collections whose ``id`` repeats across a parent."""

import json

import pytest
from pydantic import ValidationError
from test_notification_evidence import run_operations, zapier

from automationbench.schema.mailchimp import generate_member_id
from automationbench.tools.zapier.mailchimp.subscribers import (
    mailchimp_add_subscriber,
    mailchimp_add_tag_to_subscriber,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import RecordWriteSource
from automationbench_v1.contracts.record_writes import capture_record_writes

MEMBER = generate_member_id("ada@example.com")  # the simulator reuses it in every list


def world():
    return {"mailchimp": {
        "audiences": [{"id": "list_news", "name": "Newsletter"}, {"id": "list_vip", "name": "VIP"}],
        "subscribers": [{"id": MEMBER, "email": "ada@example.com", "list_id": "list_news"},
                        {"id": MEMBER, "email": "ada@example.com", "list_id": "list_vip"}]}}


def tag(list_id="list_vip"):
    args = {"list_id": list_id, "email": "ada@example.com", "tag_name": "renewal"}
    return zapier("mailchimp_add_tag_to_subscriber", args,
                  lambda w: mailchimp_add_tag_to_subscriber(w, **args))


def spec(kind="update", composite=True):
    return RecordWriteSource.model_validate({"service": "mailchimp", "collection": ["subscribers"], "kind": kind,
                                             **({"identity_paths": [["list_id"], ["id"]]} if composite else {})})


def test_same_subscriber_in_two_lists_is_diffed_by_list_and_id():
    evidence = capture_record_writes(run_operations(world(), [tag()]), spec())
    assert evidence.complete, evidence.reason
    (fact,) = evidence.effects
    params = json.loads(fact.params_json)
    assert params["record_id"] == canonical_json(["list_vip", MEMBER])
    assert params["changed_fields"] == ["tags", "updated_at"] and params["record"]["list_id"] == "list_vip"


def test_plain_identity_stays_unknown_on_repeated_ids():
    evidence = capture_record_writes(run_operations(world(), [tag()]), spec(composite=False))
    assert not evidence.complete and evidence.effects[0].reason == "record_writes_duplicate_identity"


def test_adding_the_member_to_a_third_list_is_a_create():
    args = {"list_id": "list_new", "email": "ada@example.com"}
    call = zapier("mailchimp_add_subscriber", args, lambda w: mailchimp_add_subscriber(w, **args))
    (fact,) = capture_record_writes(run_operations(world(), [call]), spec("create")).effects
    assert json.loads(fact.params_json)["record_id"] == canonical_json(["list_new", MEMBER])


def test_identity_paths_are_validated_and_omitted_when_absent():
    assert "identity_paths" not in spec(composite=False).model_dump(mode="json")
    for paths in ([["id"]], [["list_id"], ["nope"]], [["list_id"], ["tags"]], [["id"], ["id"]]):
        with pytest.raises(ValidationError, match="record_writes_identity_paths_invalid"):
            RecordWriteSource.model_validate({"service": "mailchimp", "collection": ["subscribers"],
                                              "kind": "update", "identity_paths": paths})
    with pytest.raises(ValidationError, match="record_writes_identity_paths_invalid"):
        RecordWriteSource.model_validate({"service": "monday", "collection": ["actions", "create_item"],
                                          "kind": "create", "identity_paths": [["id"], ["action_key"]]})
