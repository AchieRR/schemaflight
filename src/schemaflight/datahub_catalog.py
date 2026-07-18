from __future__ import annotations

from typing import Any, Protocol


class IncompleteEvidenceError(RuntimeError):
    """Raised when DataHub reports evidence that the adapter cannot return completely."""


class InvokableTool(Protocol):
    def invoke(self, payload: dict[str, Any]) -> Any: ...


class AgentContextCatalog:
    """Catalog adapter backed by the official DataHub Agent Context Kit tools."""

    REQUIRED_TOOLS = {
        "get_entities",
        "list_schema_fields",
        "get_lineage",
        "get_dataset_queries",
    }

    def __init__(self, tools: dict[str, InvokableTool]) -> None:
        missing = self.REQUIRED_TOOLS.difference(tools)
        if missing:
            raise ValueError(f"Missing DataHub Agent Context tools: {', '.join(sorted(missing))}")
        self._tools = tools
        self._assets: dict[str, dict[str, Any]] = {}
        self._queries: dict[str, dict[str, str]] = {}

    @classmethod
    def connect(
        cls,
        *,
        server: str,
        token: str | None = None,
        include_mutations: bool = False,
    ) -> "AgentContextCatalog":
        try:
            from datahub.sdk import DataHubClient
            from datahub_agent_context.langchain_tools import build_langchain_tools
        except ImportError as error:
            raise RuntimeError(
                "Live DataHub mode requires the 'datahub' optional dependency."
            ) from error

        client = DataHubClient(server=server, token=token)
        built_tools = build_langchain_tools(client, include_mutations=include_mutations)
        return cls({tool.name: tool for tool in built_tools})

    def asset(self, urn: str) -> dict[str, Any]:
        if urn in self._assets:
            return self._assets[urn]

        response = self._tools["get_entities"].invoke({"urns": [urn]})
        if not isinstance(response, list) or not response:
            raise ValueError(f"DataHub returned no entity for {urn!r}")
        entity = response[0]
        if error := entity.get("error"):
            raise ValueError(f"DataHub could not read {urn!r}: {error}")

        fields: list[dict[str, Any]] = []
        if urn.startswith("urn:li:dataset:"):
            fields = self._load_schema_fields(urn)
            self._load_queries(urn)

        asset = {
            "urn": urn,
            "name": entity.get("name") or entity.get("properties", {}).get("name") or urn,
            "owners": self._owner_names(entity),
            "fields": fields,
        }
        self._assets[urn] = asset
        return asset

    def downstream(self, urn: str, field: str) -> list[dict[str, str | None]]:
        if not urn.startswith("urn:li:dataset:"):
            return []
        response = self._tools["get_lineage"].invoke(
            {
                "urn": urn,
                "column": field,
                "upstream": False,
                "max_hops": 1,
                "max_results": 100,
                "offset": 0,
            }
        )
        downstreams = response.get("downstreams", {})
        results = downstreams.get("searchResults", [])
        offset = int(downstreams.get("offset", 0))
        returned = int(downstreams.get("returned", len(results)))
        total = int(downstreams.get("total", offset + returned))
        if downstreams.get("hasMore") or total > offset + returned:
            raise IncompleteEvidenceError(
                f"DataHub lineage for {urn!r}.{field} is incomplete: "
                f"received {offset + returned} of {total}; narrow the graph before compiling"
            )
        edges: list[dict[str, str | None]] = []
        for result in results:
            entity = result.get("entity", {})
            downstream_urn = entity.get("urn")
            if not downstream_urn:
                continue
            columns = result.get("lineageColumns") or [None]
            edges.extend(
                {
                    "upstream_urn": urn,
                    "upstream_field": field,
                    "downstream_urn": downstream_urn,
                    "downstream_field": column,
                }
                for column in columns
            )
        return edges

    def queries(self) -> tuple[dict[str, str], ...]:
        return tuple(self._queries[key] for key in sorted(self._queries))

    def publish_decision(
        self,
        *,
        source_urn: str,
        source_name: str,
        source_field: str,
        target_field: str,
        content: str,
    ) -> str:
        tool = self._tools.get("save_document")
        if tool is None:
            raise RuntimeError(
                "Decision write-back requires a catalog connected with mutations enabled."
            )
        response = tool.invoke(
            {
                "document_type": "Decision",
                "title": f"SchemaFlight: {source_name}.{source_field} to {target_field}",
                "content": content,
                "topics": ["schemaflight", "schema-migration", "lineage"],
                "related_assets": [source_urn],
            }
        )
        if not response.get("success") or not response.get("urn"):
            raise RuntimeError(f"DataHub decision write-back failed: {response}")
        return str(response["urn"])

    def _load_queries(self, urn: str) -> None:
        start = 0
        while True:
            response = self._tools["get_dataset_queries"].invoke(
                {"urn": urn, "column": None, "source": None, "start": start, "count": 100}
            )
            page = response.get("queries", [])
            for query in page:
                query_urn = query.get("urn", "")
                query_id = query_urn.rsplit(":", 1)[-1] or f"query-{len(self._queries) + 1}"
                statement = query.get("properties", {}).get("statement", {}).get("value")
                if statement:
                    self._queries[query_id] = {
                        "id": query_id,
                        "asset_urn": urn,
                        "sql": statement,
                    }
            total = int(response.get("total", len(page)))
            start += len(page)
            if start >= total:
                return
            if not page:
                raise IncompleteEvidenceError(
                    f"DataHub query evidence for {urn!r} stopped at {start} of {total}"
                )

    def _load_schema_fields(self, urn: str) -> list[dict[str, Any]]:
        offset = 0
        fields: list[dict[str, Any]] = []
        while True:
            response = self._tools["list_schema_fields"].invoke(
                {"urn": urn, "keywords": None, "limit": 100, "offset": offset}
            )
            page = response.get("fields", [])
            fields.extend(self._clean_field(field) for field in page)
            remaining = response.get("remainingCount")
            if remaining is None:
                total = int(response.get("totalFields", len(fields)))
                remaining = max(0, total - len(fields))
            if int(remaining) <= 0:
                return fields
            if not page:
                raise IncompleteEvidenceError(
                    f"DataHub schema evidence for {urn!r} stopped with {remaining} fields remaining"
                )
            offset += len(page)

    @staticmethod
    def _clean_field(field: dict[str, Any]) -> dict[str, Any]:
        tags = [
            item.get("tag", {}).get("properties", {}).get("name")
            or item.get("tag", {}).get("urn", "").rsplit(":", 1)[-1]
            for item in field.get("tags", {}).get("tags", [])
        ]
        return {
            "name": field.get("fieldPath") or field.get("name"),
            "type": field.get("nativeDataType") or field.get("type") or "VARCHAR",
            "nullable": field.get("nullable", True),
            "tags": [tag for tag in tags if tag],
        }

    @staticmethod
    def _owner_names(entity: dict[str, Any]) -> list[str]:
        owners: list[str] = []
        for entry in entity.get("ownership", {}).get("owners", []):
            owner = entry.get("owner", {})
            name = (
                owner.get("properties", {}).get("displayName")
                or owner.get("properties", {}).get("name")
                or owner.get("urn", "").rsplit(":", 1)[-1]
            )
            if name:
                owners.append(name)
        return owners
