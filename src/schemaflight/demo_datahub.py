from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DemoQuery:
    urn: str
    query_id: str
    sql: str
    subject_urns: tuple[str, ...]


def seed_demo_catalog(
    *,
    server: str,
    token: str | None = None,
    _client_type: type[Any] | None = None,
    _dataset_type: type[Any] | None = None,
    _tag_type: type[Any] | None = None,
    _emit_mode: Any | None = None,
    _query_writer: Any | None = None,
) -> dict[str, Any]:
    """Upsert the deterministic SchemaFlight demo graph through the official SDK."""
    if _client_type is None or _dataset_type is None or _tag_type is None or _emit_mode is None:
        try:
            from datahub.emitter.rest_emitter import EmitMode
            from datahub.sdk.dataset import Dataset
            from datahub.sdk.main_client import DataHubClient
            from datahub.sdk.tag import Tag
        except ImportError as error:
            raise RuntimeError(
                "Seeding DataHub requires the 'datahub' optional dependency."
            ) from error
        _client_type = DataHubClient
        _dataset_type = Dataset
        _tag_type = Tag
        _emit_mode = EmitMode.SYNC_WAIT

    client = _client_type(server=server, token=token)
    client.test_connection()

    pii_tag = _tag_type(
        name="PII",
        display_name="PII",
        description="Personally identifiable information used by the SchemaFlight demo.",
    )
    client.entities.upsert(pii_tag, emit_mode=_emit_mode)

    source = _dataset_type(
        platform="duckdb",
        name="shop.customer",
        display_name="shop.customer",
        description="Source customer table for the SchemaFlight demo.",
        schema=[
            ("customer_id", "BIGINT", "Stable customer identifier."),
            ("email", "VARCHAR", "Customer email address."),
            ("created_at", "TIMESTAMP", "Customer creation time."),
        ],
        owners=["data-platform"],
    )
    source["email"].set_tags([str(pii_tag.urn)])

    model = _dataset_type(
        platform="duckdb",
        name="analytics.customer_360",
        display_name="analytics.customer_360",
        description="Customer model downstream of shop.customer.",
        schema=[
            ("customer_id", "BIGINT"),
            ("email", "VARCHAR"),
        ],
        owners=["analytics"],
        upstreams={source.urn: {"email": ["email"]}},
    )
    consumer = _dataset_type(
        platform="duckdb",
        name="growth.retention_export",
        display_name="growth.retention_export",
        description="Retention export downstream of the customer model.",
        schema=[
            ("customer_id", "BIGINT"),
            ("email", "VARCHAR"),
        ],
        owners=["growth"],
        upstreams={model.urn: {"email": ["email"]}},
    )

    datasets = (source, model, consumer)
    for dataset in datasets:
        client.entities.upsert(dataset, emit_mode=_emit_mode)

    query = DemoQuery(
        urn="urn:li:query:retention-export",
        query_id="retention-export",
        sql="SELECT customer_id, email FROM analytics.customer_360",
        subject_urns=(str(model.urn),),
    )
    writer = _query_writer or _write_demo_query
    writer(server=server, token=token, query=query, emit_mode=_emit_mode)

    return {
        "datasets_upserted": len(datasets),
        "dataset_urns": [str(dataset.urn) for dataset in datasets],
        "queries_upserted": 1,
        "query_urns": [query.urn],
        "tags_upserted": 1,
        "tag_urns": [str(pii_tag.urn)],
    }


def _build_demo_query_mcps(query: DemoQuery) -> list[Any]:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import (
        AuditStampClass,
        QueryKeyClass,
        QueryPropertiesClass,
        QueryStatementClass,
        QuerySubjectClass,
        QuerySubjectsClass,
    )

    stamp = AuditStampClass(time=1784390400000, actor="urn:li:corpuser:schemaflight")
    return [
        MetadataChangeProposalWrapper(
            entityUrn=query.urn,
            aspect=QueryKeyClass(id=query.query_id),
        ),
        MetadataChangeProposalWrapper(
            entityUrn=query.urn,
            aspect=QueryPropertiesClass(
                statement=QueryStatementClass(value=query.sql, language="SQL"),
                source="MANUAL",
                created=stamp,
                lastModified=stamp,
                name="SchemaFlight retention export",
            ),
        ),
        MetadataChangeProposalWrapper(
            entityUrn=query.urn,
            aspect=QuerySubjectsClass(
                subjects=[QuerySubjectClass(entity=urn) for urn in query.subject_urns]
            ),
        ),
    ]


def _write_demo_query(*, server: str, token: str | None, query: DemoQuery, emit_mode: Any) -> None:
    from datahub.emitter.rest_emitter import DatahubRestEmitter

    emitter = DatahubRestEmitter(gms_server=server, token=token)
    emitter.emit_mcps(_build_demo_query_mcps(query), emit_mode=emit_mode)
