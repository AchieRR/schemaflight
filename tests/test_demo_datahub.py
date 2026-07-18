from typing import Any

from schemaflight.demo_datahub import seed_demo_catalog


class StubField:
    def __init__(self) -> None:
        self.tags: list[str] = []

    def set_tags(self, tags: list[str]) -> None:
        self.tags = tags


class StubDataset:
    def __init__(self, **payload: Any) -> None:
        self.payload = payload
        self.urn = f"urn:stub:{payload['name']}"
        self.fields = {name: StubField() for name, *_ in payload["schema"]}

    def __getitem__(self, field: str) -> StubField:
        return self.fields[field]


class StubTag:
    def __init__(self, **payload: Any) -> None:
        self.payload = payload
        self.urn = f"urn:li:tag:{payload['name']}"


class StubEntities:
    def __init__(self) -> None:
        self.upserted: list[tuple[Any, Any]] = []

    def upsert(self, entity: Any, *, emit_mode: Any) -> None:
        self.upserted.append((entity, emit_mode))


class StubClient:
    last: "StubClient | None" = None

    def __init__(self, *, server: str, token: str | None) -> None:
        self.server = server
        self.token = token
        self.entities = StubEntities()
        self.connected = False
        type(self).last = self

    def test_connection(self) -> None:
        self.connected = True


def test_demo_seed_builds_tagged_two_hop_column_lineage() -> None:
    written_queries: list[Any] = []

    def record_query(**payload: Any) -> None:
        written_queries.append(payload)

    summary = seed_demo_catalog(
        server="http://localhost:8080",
        token="secret-not-returned",
        _client_type=StubClient,
        _dataset_type=StubDataset,
        _tag_type=StubTag,
        _emit_mode="sync-wait",
        _query_writer=record_query,
    )

    client = StubClient.last
    assert client is not None
    assert client.connected is True
    pii_tag, source, model, consumer = [item for item, _ in client.entities.upserted]
    assert pii_tag.payload == {
        "name": "PII",
        "display_name": "PII",
        "description": "Personally identifiable information used by the SchemaFlight demo.",
    }
    assert [item.payload["name"] for item in (source, model, consumer)] == [
        "shop.customer",
        "analytics.customer_360",
        "growth.retention_export",
    ]
    assert [mode for _, mode in client.entities.upserted] == ["sync-wait"] * 4
    assert source.fields["email"].tags == ["urn:li:tag:PII"]
    assert model.payload["upstreams"] == {source.urn: {"email": ["email"]}}
    assert consumer.payload["upstreams"] == {model.urn: {"email": ["email"]}}
    assert summary == {
        "datasets_upserted": 3,
        "dataset_urns": [source.urn, model.urn, consumer.urn],
        "queries_upserted": 1,
        "query_urns": ["urn:li:query:retention-export"],
        "tags_upserted": 1,
        "tag_urns": ["urn:li:tag:PII"],
    }
    assert written_queries[0]["query"].sql == (
        "SELECT customer_id, email FROM analytics.customer_360"
    )
    assert written_queries[0]["query"].subject_urns == (model.urn,)
