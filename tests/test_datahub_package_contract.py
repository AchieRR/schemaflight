from typing import Any

import pytest

from schemaflight.demo_datahub import DemoQuery, _build_demo_query_mcps, seed_demo_catalog


datahub_dataset = pytest.importorskip("datahub.sdk.dataset")
DataHubDataset = datahub_dataset.Dataset


class RecordingEntities:
    def __init__(self) -> None:
        self.proposal_counts: list[int] = []

    def upsert(self, dataset: Any, *, emit_mode: Any) -> None:
        self.proposal_counts.append(len(list(dataset.as_mcps())))


class RecordingClient:
    last: "RecordingClient | None" = None

    def __init__(self, *, server: str, token: str | None) -> None:
        self.entities = RecordingEntities()
        type(self).last = self

    def test_connection(self) -> None:
        return None


def test_demo_entities_serialize_with_the_pinned_official_datahub_sdk() -> None:
    result = seed_demo_catalog(
        server="http://localhost:8080",
        _client_type=RecordingClient,
        _dataset_type=DataHubDataset,
        _emit_mode="sync-wait",
        _query_writer=lambda **payload: None,
    )

    client = RecordingClient.last
    assert client is not None
    assert result["datasets_upserted"] == 3
    assert all(count > 0 for count in client.entities.proposal_counts)


def test_demo_query_serializes_with_official_datahub_aspects() -> None:
    query = DemoQuery(
        urn="urn:li:query:retention-export",
        query_id="retention-export",
        sql="SELECT email FROM analytics.customer_360",
        subject_urns=("urn:li:dataset:(urn:li:dataPlatform:duckdb,analytics.customer_360,PROD)",),
    )

    proposals = [wrapper.make_mcp() for wrapper in _build_demo_query_mcps(query)]

    assert len(proposals) == 3
    assert {proposal.aspectName for proposal in proposals} == {
        "queryKey",
        "queryProperties",
        "querySubjects",
    }
