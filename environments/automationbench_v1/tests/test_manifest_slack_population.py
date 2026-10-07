"""Slack messages as an initial population via a composite (channel_id, ts) identity."""

import pytest
from pydantic import ValidationError

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.populations import (
    InitialCollectionSource,
    capture_population,
    native_record_id,
)

SOURCE = {"path": ["task_evidence", "initial", "slack", "messages"], "identity_paths": [["channel_id"], ["ts"]],
          "fields": {"Channel": ["channel_id"], "Ts": ["ts"], "User": ["user_id"], "Text": ["text"]},
          "key_fields": ["Channel", "Ts"], "required_fields": ["Text"]}


def material(messages):
    return {"task_evidence": {"initial": {"slack": {"messages": messages}}}}


def message(ts, text, channel="Cbreaks", user="Ualice"):
    return {"channel_id": channel, "ts": ts, "user_id": user, "text": text}


def test_slack_messages_form_a_keyed_population():
    spec = InitialCollectionSource.model_validate(SOURCE)
    evidence = capture_population(material([message("1767000000.000100", "Break 2:30 PM please"),
                                            message("1767003600.000200", "Break at noon", user="Ubob")]), spec)
    assert evidence.status == "qualified" and evidence.closed and len(evidence.rows) == 2
    row = evidence.rows[0]
    assert native_record_id(row) == canonical_json(["Cbreaks", "1767000000.000100"])  # matches Slack effect ids


def test_duplicate_or_missing_identity_is_not_qualified():
    spec = InitialCollectionSource.model_validate(SOURCE)
    duplicate = capture_population(material([message("1", "a"), message("1", "b")]), spec)
    assert duplicate.status == "unavailable"
    missing = capture_population(material([{"channel_id": "C", "text": "no ts", "user_id": "U"}]), spec)
    assert missing.status == "partial" and not missing.closed


@pytest.mark.parametrize("paths", [[["text"], ["nope"]], [["reactions"]], [["channel_id", "x"]]])
def test_identity_paths_must_be_required_string_fields(paths):
    with pytest.raises(ValidationError, match="population_native_identity_required"):
        InitialCollectionSource.model_validate({**SOURCE, "identity_paths": paths})


def test_legacy_declarations_omit_identity_paths():
    legacy = InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "helpcrunch", "customers"], "fields": {"Email": ["email"]},
        "key_fields": ["Email"]})
    assert "identity_paths" not in legacy.model_dump(mode="json")
    with pytest.raises(ValidationError, match="population_native_identity_required"):
        InitialCollectionSource.model_validate({**SOURCE, "identity_paths": []})
