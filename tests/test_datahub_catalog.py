from collections.abc import Callable
from typing import Any

import pytest

from schemaflight import ChangeRequest, SchemaFlight
from schemaflight.datahub_catalog import AgentContextCatalog, IncompleteEvidenceError


SOURCE = "urn:li:dataset:(urn:li:dataPlatform:duckdb,shop.customer,PROD)"
MODEL = "urn:li:dataset:(urn:li:dataPlatform:duckdb,analytics.customer_360,PROD)"
DASHBOARD = "urn:li:dashboard:(looker,retention_dashboard)"


class StubTool:
    def __init__(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any]) -> Any:
        self.calls.append(payload)
        return self._handler(payload)


def test_agent_context_catalog_drives_the_compiler_with_official_tool_shapes() -> None:
    entities = {
        SOURCE: {
            "urn": SOURCE,
            "name": "shop.customer",
            "ownership": {"owners": [{"owner": {"urn": "urn:li:corpGroup:data-platform"}}]},
        },
        MODEL: {
            "urn": MODEL,
            "name": "analytics.customer_360",
            "ownership": {"owners": [{"owner": {"urn": "urn:li:corpGroup:analytics"}}]},
        },
        DASHBOARD: {
            "urn": DASHBOARD,
            "name": "retention_dashboard",
            "ownership": {"owners": [{"owner": {"urn": "urn:li:corpGroup:growth"}}]},
        },
    }
    get_entities = StubTool(lambda payload: [entities[urn] for urn in payload["urns"]])

    def schema_handler(payload: dict[str, Any]) -> dict[str, Any]:
        if payload["urn"] == SOURCE:
            return {
                "urn": SOURCE,
                "fields": [
                    {"fieldPath": "customer_id", "nativeDataType": "BIGINT", "nullable": False},
                    {
                        "fieldPath": "email",
                        "nativeDataType": "VARCHAR",
                        "nullable": False,
                        "tags": {"tags": [{"tag": {"properties": {"name": "PII"}}}]},
                    },
                ],
            }
        return {
            "urn": MODEL,
            "fields": [
                {"fieldPath": "customer_id", "nativeDataType": "BIGINT", "nullable": False},
                {"fieldPath": "email", "nativeDataType": "VARCHAR", "nullable": False},
            ],
        }

    list_schema_fields = StubTool(schema_handler)

    def lineage_handler(payload: dict[str, Any]) -> dict[str, Any]:
        if payload["urn"] == SOURCE:
            results = [{"entity": entities[MODEL], "degree": 1, "lineageColumns": ["email"]}]
        elif payload["urn"] == MODEL:
            results = [{"entity": entities[DASHBOARD], "degree": 1}]
        else:
            results = []
        return {"downstreams": {"searchResults": results, "hasMore": False}}

    get_lineage = StubTool(lineage_handler)

    def query_handler(payload: dict[str, Any]) -> dict[str, Any]:
        if payload["urn"] != MODEL:
            return {"total": 0, "queries": []}
        return {
            "total": 1,
            "queries": [
                {
                    "urn": "urn:li:query:retention-export",
                    "properties": {
                        "statement": {
                            "value": "SELECT customer_id, email FROM analytics.customer_360"
                        }
                    },
                }
            ],
        }

    get_dataset_queries = StubTool(query_handler)
    catalog = AgentContextCatalog(
        {
            "get_entities": get_entities,
            "list_schema_fields": list_schema_fields,
            "get_lineage": get_lineage,
            "get_dataset_queries": get_dataset_queries,
        }
    )
    request = ChangeRequest(
        dataset_urn=SOURCE,
        operation="rename_column",
        source_field="email",
        target_field="primary_email",
        dialect="duckdb",
    )

    bundle = SchemaFlight(catalog).compile(request)

    assert [asset.name for asset in bundle.blast_radius.assets] == [
        "analytics.customer_360",
        "retention_dashboard",
    ]
    assert bundle.manifest["source"]["field_tags"] == ["PII"]
    assert "primary_email" in bundle.files["query_patches/retention-export.sql"]
    assert len(get_lineage.calls) == 2
    assert get_lineage.calls[0] == {
        "urn": SOURCE,
        "column": "email",
        "upstream": False,
        "max_hops": 1,
        "max_results": 100,
        "offset": 0,
    }


def test_decision_writeback_is_explicit_and_uses_the_agent_context_document_tool() -> None:
    save_document = StubTool(
        lambda payload: {
            "success": True,
            "urn": "urn:li:document:schemaflight-email-migration",
        }
    )
    catalog = AgentContextCatalog(
        {
            "get_entities": StubTool(lambda payload: []),
            "list_schema_fields": StubTool(lambda payload: {}),
            "get_lineage": StubTool(lambda payload: {}),
            "get_dataset_queries": StubTool(lambda payload: {}),
            "save_document": save_document,
        }
    )

    result = catalog.publish_decision(
        source_urn=SOURCE,
        source_name="shop.customer",
        source_field="email",
        target_field="primary_email",
        content="# Migration decision\n\nDirect rename rejected.",
    )

    assert result == "urn:li:document:schemaflight-email-migration"
    assert save_document.calls == [
        {
            "document_type": "Decision",
            "title": "SchemaFlight: shop.customer.email to primary_email",
            "content": "# Migration decision\n\nDirect rename rejected.",
            "topics": ["schemaflight", "schema-migration", "lineage"],
            "related_assets": [SOURCE],
        }
    ]


def test_non_dataset_assets_are_terminal_for_field_lineage() -> None:
    get_lineage = StubTool(lambda payload: {"downstreams": {"searchResults": [], "hasMore": False}})
    catalog = AgentContextCatalog(
        {
            "get_entities": StubTool(lambda payload: []),
            "list_schema_fields": StubTool(lambda payload: {}),
            "get_lineage": get_lineage,
            "get_dataset_queries": StubTool(lambda payload: {}),
        }
    )

    assert catalog.downstream(DASHBOARD, "email") == []
    assert get_lineage.calls == []


def test_live_lineage_fails_closed_when_the_tool_reports_more_results() -> None:
    catalog = AgentContextCatalog(
        {
            "get_entities": StubTool(lambda payload: []),
            "list_schema_fields": StubTool(lambda payload: {}),
            "get_lineage": StubTool(
                lambda payload: {
                    "downstreams": {
                        "searchResults": [{"entity": {"urn": MODEL}}],
                        "hasMore": True,
                    }
                }
            ),
            "get_dataset_queries": StubTool(lambda payload: {}),
        }
    )

    with pytest.raises(IncompleteEvidenceError, match="lineage"):
        catalog.downstream(SOURCE, "email")


def test_live_lineage_fails_closed_when_total_exceeds_returned_results() -> None:
    catalog = AgentContextCatalog(
        {
            "get_entities": StubTool(lambda payload: []),
            "list_schema_fields": StubTool(lambda payload: {}),
            "get_lineage": StubTool(
                lambda payload: {
                    "downstreams": {
                        "searchResults": [{"entity": {"urn": MODEL}}],
                        "total": 2,
                        "offset": 0,
                        "returned": 1,
                        "hasMore": False,
                    }
                }
            ),
            "get_dataset_queries": StubTool(lambda payload: {}),
        }
    )

    with pytest.raises(IncompleteEvidenceError, match="1 of 2"):
        catalog.downstream(SOURCE, "email")


def test_live_schema_and_queries_are_paginated_to_completion() -> None:
    list_schema_fields = StubTool(
        lambda payload: {
            "fields": [
                {
                    "fieldPath": "customer_id" if payload["offset"] == 0 else "email",
                    "nativeDataType": "BIGINT" if payload["offset"] == 0 else "VARCHAR",
                }
            ],
            "remainingCount": 1 if payload["offset"] == 0 else 0,
        }
    )

    def query_page(payload: dict[str, Any]) -> dict[str, Any]:
        index = payload["start"]
        queries = []
        if index < 2:
            queries = [
                {
                    "urn": f"urn:li:query:q-{index}",
                    "properties": {"statement": {"value": f"SELECT {index}"}},
                }
            ]
        return {"total": 2, "queries": queries}

    catalog = AgentContextCatalog(
        {
            "get_entities": StubTool(lambda payload: [{"urn": SOURCE, "name": "shop.customer"}]),
            "list_schema_fields": list_schema_fields,
            "get_lineage": StubTool(lambda payload: {}),
            "get_dataset_queries": StubTool(query_page),
        }
    )

    asset = catalog.asset(SOURCE)

    assert [field["name"] for field in asset["fields"]] == ["customer_id", "email"]
    assert [query["id"] for query in catalog.queries()] == ["q-0", "q-1"]
    assert [call["offset"] for call in list_schema_fields.calls] == [0, 1]
