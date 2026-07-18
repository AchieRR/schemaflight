import json
from pathlib import Path

import duckdb
import pytest

from schemaflight import ChangeRequest, SchemaFlight, SnapshotCatalog


FIXTURES = Path(__file__).parents[1] / "examples" / "ecommerce"


def test_rename_with_downstream_usage_compiles_a_safe_staged_bundle() -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")

    bundle = SchemaFlight(catalog).compile(request)

    assert bundle.risk.level == "high"
    assert bundle.risk.direct_rename_allowed is False
    assert [asset.name for asset in bundle.blast_radius.assets] == [
        "analytics.customer_360",
        "retention_dashboard",
    ]
    assert [phase.name for phase in bundle.phases] == [
        "expand",
        "migrate",
        "contract",
    ]
    assert 'ADD COLUMN "primary_email" VARCHAR' in bundle.files["01_expand.sql"]
    assert "primary_email" in bundle.files["query_patches/retention-export.sql"]
    assert bundle.manifest["evidence"]["lineage_hops"] == 2
    assert bundle.manifest["source"]["field_tags"] == ["PII"]


def test_generated_sql_stays_valid_through_the_full_duckdb_lifecycle() -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")
    bundle = SchemaFlight(catalog).compile(request)
    database = duckdb.connect(":memory:")
    database.execute("CREATE SCHEMA shop")
    database.execute(
        """
        CREATE TABLE shop.customer (
            customer_id BIGINT NOT NULL,
            email VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    database.execute(
        "INSERT INTO shop.customer VALUES (1, 'ada@example.test', '2026-07-18 12:00:00')"
    )

    database.execute(bundle.files["01_expand.sql"])
    compatible = database.execute(
        "SELECT customer_id, email, primary_email FROM shop.customer_compat"
    ).fetchone()
    assert compatible == (1, "ada@example.test", "ada@example.test")
    assert [item[0] for item in database.description] == [
        "customer_id",
        "email",
        "primary_email",
    ]

    database.execute("UPDATE shop.customer SET primary_email = 'wrong@example.test'")
    assert database.execute(bundle.files["checks.sql"]).fetchone() == (1,)
    database.execute("UPDATE shop.customer SET primary_email = email")
    database.execute(bundle.files["02_migrate.sql"])
    assert database.execute(bundle.files["checks.sql"]).fetchone() == (0,)
    migrated = database.execute("SELECT customer_id, primary_email FROM shop.customer").fetchone()
    assert migrated == (1, "ada@example.test")

    database.execute(bundle.files["03_contract.sql"])
    assert database.execute(
        "SELECT customer_id, primary_email FROM shop.customer_compat"
    ).fetchone() == (1, "ada@example.test")
    with pytest.raises(duckdb.BinderException):
        database.execute("SELECT email FROM shop.customer")


def test_existing_target_field_is_rejected_before_artifacts_are_generated(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        (FIXTURES / "catalog.json")
        .read_text(encoding="utf-8")
        .replace(
            '{"name": "created_at", "type": "TIMESTAMP", "nullable": false, "tags": []}',
            '{"name": "primary_email", "type": "VARCHAR", "nullable": true, "tags": []},'
            '\n        {"name": "created_at", "type": "TIMESTAMP", "nullable": false, "tags": []}',
            1,
        ),
        encoding="utf-8",
    )
    catalog = SnapshotCatalog.from_file(catalog_path)
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")

    try:
        SchemaFlight(catalog).compile(request)
    except ValueError as error:
        assert str(error) == "Dataset 'shop.customer' already has field 'primary_email'"
    else:
        raise AssertionError("target-field collision should fail compilation")


def test_bundle_includes_owner_routing_checks_rollback_and_a_decision_record() -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")

    bundle = SchemaFlight(catalog).compile(request)

    decision = bundle.files["migration-decision.md"]
    assert "Direct rename rejected" in decision
    assert "analytics.customer_360" in decision
    assert "@analytics" in decision
    assert "retention_dashboard" in decision
    assert "@growth" in decision
    assert "rollback.sql" in bundle.files
    assert "IS DISTINCT FROM" in bundle.files["checks.sql"]
    assert bundle.manifest["owner_routes"] == {
        "analytics": ["analytics.customer_360"],
        "growth": ["retention_dashboard"],
    }


def test_bundle_contains_a_self_contained_accessible_evidence_report() -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")

    report = SchemaFlight(catalog).compile(request).files["report.html"]

    assert report.count("<h1") == 1
    assert '<a class="skip-link" href="#main">' in report
    assert '<main id="main">' in report
    assert "DATAHUB EVIDENCE // 02 HOPS" in report
    assert "shop.customer.email" in report
    assert "analytics.customer_360" in report
    assert "retention_dashboard" in report
    assert "prefers-reduced-motion" in report
    assert "https://" not in report


def test_bundle_rejects_an_artifact_path_outside_the_destination(tmp_path: Path) -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")
    bundle = SchemaFlight(catalog).compile(request)
    bundle.files["../escape.sql"] = "SELECT 1;\n"

    with pytest.raises(ValueError, match="escapes output directory"):
        bundle.write_to(tmp_path / "bundle")

    assert not (tmp_path / "escape.sql").exists()


def test_lineage_hops_measure_depth_instead_of_branch_count() -> None:
    source = "urn:source"
    first = "urn:first"
    second = "urn:second"
    catalog = SnapshotCatalog(
        {
            "assets": [
                {
                    "urn": source,
                    "name": "source",
                    "owners": [],
                    "fields": [{"name": "email", "type": "VARCHAR", "tags": []}],
                },
                {"urn": first, "name": "first", "owners": [], "fields": []},
                {"urn": second, "name": "second", "owners": [], "fields": []},
            ],
            "lineage": [
                {
                    "upstream_urn": source,
                    "upstream_field": "email",
                    "downstream_urn": first,
                    "downstream_field": "email",
                },
                {
                    "upstream_urn": source,
                    "upstream_field": "email",
                    "downstream_urn": second,
                    "downstream_field": "email",
                },
                {
                    "upstream_urn": first,
                    "upstream_field": "email",
                    "downstream_urn": source,
                    "downstream_field": "email",
                },
            ],
            "queries": [],
        }
    )
    request = ChangeRequest(
        dataset_urn=source,
        operation="rename_column",
        source_field="email",
        target_field="primary_email",
        dialect="duckdb",
    )

    bundle = SchemaFlight(catalog).compile(request)

    assert bundle.manifest["evidence"]["lineage_hops"] == 1
    assert [asset.name for asset in bundle.blast_radius.assets] == ["first", "second"]
    assert [asset.depth for asset in bundle.blast_radius.assets] == [1, 1]
    assert bundle.files["report.html"].count("HOP 01") == 2
    assert "HOP 02" not in bundle.files["report.html"]


def test_no_impact_compile_emits_a_truthful_direct_rename_bundle() -> None:
    catalog = SnapshotCatalog(
        {
            "assets": [
                {
                    "urn": "urn:source",
                    "name": "shop.customer",
                    "owners": [],
                    "fields": [{"name": "email", "type": "VARCHAR", "tags": []}],
                }
            ],
            "lineage": [],
            "queries": [],
        }
    )
    request = ChangeRequest(
        dataset_urn="urn:source",
        operation="rename_column",
        source_field="email",
        target_field="primary_email",
        dialect="duckdb",
    )

    bundle = SchemaFlight(catalog).compile(request)

    assert bundle.risk.direct_rename_allowed is True
    assert [phase.name for phase in bundle.phases] == ["direct"]
    assert "01_direct.sql" in bundle.files
    assert "Direct rename allowed" in bundle.files["migration-decision.md"]
    assert "DIRECT RENAME ALLOWED" in bundle.files["report.html"]
    assert "DIRECT RENAME REJECTED" not in bundle.files["report.html"]


def test_source_query_usage_rejects_a_direct_rename_without_lineage() -> None:
    source = "urn:source"
    catalog = SnapshotCatalog(
        {
            "assets": [
                {
                    "urn": source,
                    "name": "shop.customer",
                    "owners": [],
                    "fields": [{"name": "email", "type": "VARCHAR", "tags": []}],
                }
            ],
            "lineage": [],
            "queries": [
                {
                    "id": "source-reader",
                    "asset_urn": source,
                    "sql": "SELECT email FROM shop.customer",
                }
            ],
        }
    )
    request = ChangeRequest(
        dataset_urn=source,
        operation="rename_column",
        source_field="email",
        target_field="primary_email",
        dialect="duckdb",
    )

    bundle = SchemaFlight(catalog).compile(request)

    assert bundle.risk.direct_rename_allowed is False
    assert [phase.name for phase in bundle.phases] == ["expand", "migrate", "contract"]
    assert "query_patches/source-reader.sql" in bundle.files
    assert bundle.manifest["evidence"]["query_ids"] == ["source-reader"]


def test_query_patch_rewrites_only_unqualified_column_references(tmp_path: Path) -> None:
    snapshot = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
    snapshot["queries"][0]["sql"] = (
        "SELECT 'email' AS literal, other.email AS foreign_email, email "
        "FROM analytics.customer_360 -- email stays in this comment"
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(snapshot), encoding="utf-8")
    catalog = SnapshotCatalog.from_file(catalog_path)
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")

    bundle = SchemaFlight(catalog).compile(request)
    query_patch = bundle.files["query_patches/retention-export.sql"]

    assert "primary_email" in query_patch
    assert "'email'" in query_patch
    assert "other.email" in query_patch
    assert "email stays in this comment" in query_patch
    assert bundle.manifest["evidence"]["queries_requiring_review"] == ["retention-export"]


def test_unqualified_column_in_a_multi_table_query_requires_review(tmp_path: Path) -> None:
    snapshot = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
    snapshot["queries"][0]["sql"] = (
        "SELECT email FROM analytics.customer_360 JOIN other.contacts ON TRUE"
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(snapshot), encoding="utf-8")
    catalog = SnapshotCatalog.from_file(catalog_path)
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")

    bundle = SchemaFlight(catalog).compile(request)

    assert "query_patches/retention-export.sql" not in bundle.files
    assert bundle.manifest["evidence"]["queries_requiring_review"] == ["retention-export"]


@pytest.mark.parametrize(
    ("dialect", "target", "message"),
    [
        ("postgres", "primary_email", "Unsupported dialect"),
        ("duckdb", "primary_email; DROP TABLE x", "Invalid target field"),
    ],
)
def test_invalid_or_unsupported_requests_are_rejected(
    dialect: str, target: str, message: str
) -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:duckdb,shop.customer,PROD)",
        operation="rename_column",
        source_field="email",
        target_field=target,
        dialect=dialect,
    )

    with pytest.raises(ValueError, match=message):
        SchemaFlight(catalog).compile(request)


def test_recompile_removes_only_stale_managed_artifacts(tmp_path: Path) -> None:
    catalog = SnapshotCatalog.from_file(FIXTURES / "catalog.json")
    request = ChangeRequest.from_file(FIXTURES / "rename-email.json")
    output = tmp_path / "bundle"
    first = SchemaFlight(catalog).compile(request)
    first.write_to(output)
    unmanaged = output / "review-notes.txt"
    unmanaged.write_text("keep me", encoding="utf-8")

    snapshot = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
    snapshot["queries"] = []
    second = SchemaFlight(SnapshotCatalog(snapshot)).compile(request)
    second.write_to(output)

    assert not (output / "query_patches" / "retention-export.sql").exists()
    assert unmanaged.read_text(encoding="utf-8") == "keep me"
