"""Persist explicitly supplied scheduling instants; do not infer a task clock."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.buffer.posts import buffer_add_to_queue


@pytest.mark.parametrize('method', ['schedule', 'schedule_draft'])
def test_explicit_offset_schedule_survives_native_serialization(method):
    instant = datetime(2026, 10, 9, 15, tzinfo=timezone(timedelta(hours=5)))
    world = WorldState()
    response = json.loads(buffer_add_to_queue(world, 'org', 'channel', method=method, text='Public post', scheduled_at=instant))
    due = int(datetime(2026, 10, 9, 10, tzinfo=UTC).timestamp())
    assert world.buffer.posts[0].due_at == due
    restored = WorldState.model_validate_json(world.model_dump_json())
    assert restored.buffer.posts[0].due_at == due
    assert response['success'] is True


def test_missing_schedule_or_other_method_never_infers_instant():
    world = WorldState()
    buffer_add_to_queue(world, 'org', 'channel', method='schedule')
    buffer_add_to_queue(world, 'org', 'channel', method='queue', scheduled_at=datetime(2026, 10, 9, 15, tzinfo=UTC))
    assert all(p.due_at is None for p in world.buffer.posts)
