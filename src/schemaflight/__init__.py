from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from schemaflight.report import render_evidence_report


@dataclass(frozen=True)
class ChangeRequest:
    dataset_urn: str
    operation: str
    source_field: str
    target_field: str
    dialect: str

    @classmethod
    def from_file(cls, path: str | Path) -> "ChangeRequest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload)


@dataclass(frozen=True)
class Asset:
    urn: str
    name: str
    owners: tuple[str, ...]
    depth: int


@dataclass(frozen=True)
class LineageEdge:
    upstream_urn: str
    upstream_field: str
    downstream_urn: str
    downstream_field: str | None


@dataclass(frozen=True)
class BlastRadius:
    assets: tuple[Asset, ...]
    edges: tuple[LineageEdge, ...]


@dataclass(frozen=True)
class Risk:
    level: str
    direct_rename_allowed: bool


@dataclass(frozen=True)
class Phase:
    name: str


@dataclass(frozen=True)
class MigrationBundle:
    risk: Risk
    blast_radius: BlastRadius
    phases: tuple[Phase, ...]
    files: dict[str, str]
    manifest: dict[str, Any]

    def write_to(self, output: str | Path) -> Path:
        destination = Path(output).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        targets: dict[str, Path] = {}
        for relative_name, content in self.files.items():
            target = (destination / relative_name).resolve()
            if destination not in target.parents:
                raise ValueError(f"Artifact path escapes output directory: {relative_name!r}")
            targets[relative_name] = target

        previous_manifest = destination / "impact-manifest.json"
        if previous_manifest.is_file():
            try:
                previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                previous = {}
            for relative_name in previous.get("artifacts", []):
                stale = (destination / relative_name).resolve()
                if destination not in stale.parents:
                    raise ValueError(
                        f"Previous managed artifact escapes output directory: {relative_name!r}"
                    )
                if relative_name not in targets and stale.is_file():
                    stale.unlink()

        for relative_name, content in self.files.items():
            target = targets[relative_name]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        (destination / "impact-manifest.json").write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return destination


class SnapshotCatalog:
    """Read-only adapter for reproducible examples and compiler tests."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot

    @classmethod
    def from_file(cls, path: str | Path) -> "SnapshotCatalog":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def asset(self, urn: str) -> dict[str, Any]:
        for asset in self._snapshot["assets"]:
            if asset["urn"] == urn:
                return asset
        raise ValueError(f"Catalog has no asset {urn!r}")

    def downstream(self, urn: str, field: str) -> list[dict[str, str]]:
        return [
            edge
            for edge in self._snapshot.get("lineage", [])
            if edge["upstream_urn"] == urn and edge["upstream_field"] == field
        ]

    def queries(self) -> tuple[dict[str, str], ...]:
        return tuple(self._snapshot.get("queries", []))


class Catalog(Protocol):
    def asset(self, urn: str) -> dict[str, Any]: ...

    def downstream(self, urn: str, field: str) -> list[dict[str, Any]]: ...

    def queries(self) -> tuple[dict[str, str], ...]: ...


class SchemaFlight:
    """Compile one proposed schema mutation into a deterministic migration bundle."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def compile(self, request: ChangeRequest) -> MigrationBundle:
        self._validate_request(request)

        source = self._catalog.asset(request.dataset_urn)
        source_field = next(
            (field for field in source["fields"] if field["name"] == request.source_field),
            None,
        )
        if source_field is None:
            raise ValueError(f"Dataset {source['name']!r} has no field {request.source_field!r}")
        if any(field["name"] == request.target_field for field in source["fields"]):
            raise ValueError(
                f"Dataset {source['name']!r} already has field {request.target_field!r}"
            )

        impacted, lineage_edges, lineage_hops = self._trace_downstream(
            request.dataset_urn, request.source_field
        )
        impact_urns = {request.dataset_urn, *(asset.urn for asset in impacted)}
        patches, review_queries = self._query_patches(request, impact_urns)
        owner_routes = self._owner_routes(impacted)
        has_impact = bool(impacted or patches or review_queries)
        if has_impact:
            phases = tuple(Phase(name) for name in ("expand", "migrate", "contract"))
            files = self._render_staged_files(
                request,
                source,
                source_field,
                impacted,
                owner_routes,
                patches,
                review_queries,
                lineage_hops,
            )
        else:
            phases = (Phase("direct"),)
            files = self._render_direct_files(request, source, impacted, lineage_hops)

        manifest = {
            "request": {
                "operation": request.operation,
                "source_field": request.source_field,
                "target_field": request.target_field,
            },
            "source": {
                "urn": request.dataset_urn,
                "name": source["name"],
                "field_tags": list(source_field.get("tags", [])),
            },
            "evidence": {
                "lineage_hops": lineage_hops,
                "impacted_urns": [asset.urn for asset in impacted],
                "lineage_edges": [
                    {
                        "upstream_urn": edge.upstream_urn,
                        "upstream_field": edge.upstream_field,
                        "downstream_urn": edge.downstream_urn,
                        "downstream_field": edge.downstream_field,
                    }
                    for edge in lineage_edges
                ],
                "query_ids": sorted(patches),
                "queries_requiring_review": sorted(review_queries),
            },
            "owner_routes": owner_routes,
        }
        manifest["artifacts"] = sorted([*files, "impact-manifest.json"])
        return MigrationBundle(
            risk=Risk(
                level="high" if has_impact else "low",
                direct_rename_allowed=not has_impact,
            ),
            blast_radius=BlastRadius(tuple(impacted), tuple(lineage_edges)),
            phases=phases,
            files=files,
            manifest=manifest,
        )

    @staticmethod
    def _validate_request(request: ChangeRequest) -> None:
        if request.operation != "rename_column":
            raise ValueError(f"Unsupported operation {request.operation!r}")
        if request.dialect != "duckdb":
            raise ValueError(f"Unsupported dialect {request.dialect!r}; expected 'duckdb'")
        identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        if not identifier.fullmatch(request.source_field):
            raise ValueError(f"Invalid source field {request.source_field!r}")
        if not identifier.fullmatch(request.target_field):
            raise ValueError(f"Invalid target field {request.target_field!r}")

    def _trace_downstream(
        self, source_urn: str, source_field: str
    ) -> tuple[list[Asset], list[LineageEdge], int]:
        queue = [(source_urn, source_field, 0)]
        visited_nodes = {(source_urn, source_field)}
        impacted: list[Asset] = []
        impacted_urns = {source_urn}
        lineage_edges: list[LineageEdge] = []
        seen_edges: set[tuple[str, str, str, str | None]] = set()
        maximum_depth = 0

        while queue:
            urn, field, depth = queue.pop(0)
            for edge in self._catalog.downstream(urn, field):
                edge_depth = depth + 1
                downstream_node = (edge["downstream_urn"], edge["downstream_field"])
                edge_key = (
                    edge["upstream_urn"],
                    edge["upstream_field"],
                    edge["downstream_urn"],
                    edge["downstream_field"],
                )
                if edge_key not in seen_edges:
                    lineage_edges.append(LineageEdge(*edge_key))
                    seen_edges.add(edge_key)
                if edge["downstream_urn"] not in impacted_urns:
                    record = self._catalog.asset(edge["downstream_urn"])
                    impacted.append(
                        Asset(
                            urn=record["urn"],
                            name=record["name"],
                            owners=tuple(record.get("owners", [])),
                            depth=edge_depth,
                        )
                    )
                    impacted_urns.add(record["urn"])
                if downstream_node not in visited_nodes:
                    visited_nodes.add(downstream_node)
                    maximum_depth = max(maximum_depth, edge_depth)
                    downstream_urn, downstream_field = downstream_node
                    is_datahub_non_dataset = downstream_urn.startswith(
                        "urn:li:"
                    ) and not downstream_urn.startswith("urn:li:dataset:")
                    if downstream_field is not None and not is_datahub_non_dataset:
                        queue.append((downstream_urn, downstream_field, edge_depth))

        return impacted, lineage_edges, maximum_depth

    def _query_patches(
        self, request: ChangeRequest, impact_urns: set[str]
    ) -> tuple[dict[str, str], set[str]]:
        patches: dict[str, str] = {}
        review_queries: set[str] = set()
        token = re.compile(rf"\b{re.escape(request.source_field)}\b", re.IGNORECASE)
        for query in self._catalog.queries():
            if query["asset_urn"] not in impact_urns or not token.search(query["sql"]):
                continue
            try:
                statements = parse(query["sql"], read=request.dialect)
            except ParseError:
                review_queries.add(query["id"])
                continue

            changed = False
            for statement in statements:
                multi_source = len(list(statement.find_all(exp.Table))) > 1
                for column in statement.find_all(exp.Column):
                    if column.name.casefold() != request.source_field.casefold():
                        continue
                    if column.table or multi_source:
                        review_queries.add(query["id"])
                        continue
                    column.set("this", exp.to_identifier(request.target_field))
                    changed = True
            if changed:
                patches[query["id"]] = ";\n".join(
                    statement.sql(dialect=request.dialect) for statement in statements
                )
        return patches, review_queries

    def _render_staged_files(
        self,
        request: ChangeRequest,
        source: dict[str, Any],
        source_field: dict[str, Any],
        impacted: list[Asset],
        owner_routes: dict[str, list[str]],
        patches: dict[str, str],
        review_queries: set[str],
        lineage_hops: int,
    ) -> dict[str, str]:
        table = self._quote_qualified(source["name"])
        compat = self._quote_qualified(self._suffixed_name(source["name"], "_compat"))
        source_column = self._quote_identifier(request.source_field)
        target_column = self._quote_identifier(request.target_field)
        field_type = self._safe_field_type(str(source_field["type"]))
        files = {
            "01_expand.sql": (
                f"-- Expand: keep {source_column} authoritative while adding {target_column}.\n"
                f"ALTER TABLE {table} ADD COLUMN {target_column} {field_type};\n"
                f"UPDATE {table} SET {target_column} = {source_column}\n"
                f"WHERE {target_column} IS NULL;\n"
                f"CREATE OR REPLACE VIEW {compat} AS SELECT * FROM {table};\n"
            ),
            "02_migrate.sql": (
                "-- Migrate readers, apply query patches, and dual-write both fields.\n"
                f"UPDATE {table} SET {target_column} = {source_column}\n"
                f"WHERE {target_column} IS NULL;\n"
            ),
            "03_contract.sql": (
                "-- Run only after every manifest dependency has migrated.\n"
                f"DROP VIEW IF EXISTS {compat};\n"
                f"ALTER TABLE {table} DROP COLUMN {source_column};\n"
                f"CREATE OR REPLACE VIEW {compat} AS SELECT * FROM {table};\n"
            ),
            "checks.sql": (
                "-- Must return zero before the contract phase.\n"
                f"SELECT COUNT(*) AS unmigrated_rows FROM {table}\n"
                f"WHERE {target_column} IS DISTINCT FROM {source_column};\n"
            ),
            "rollback.sql": (
                "-- Safe before the contract phase; the original column remains authoritative.\n"
                f"DROP VIEW IF EXISTS {compat};\n"
                f"ALTER TABLE {table} DROP COLUMN {target_column};\n"
                f"CREATE OR REPLACE VIEW {compat} AS SELECT * FROM {table};\n"
                "-- After contract, restore from a verified backup before dropping the new column.\n"
            ),
            "migration-decision.md": self._decision_document(
                request,
                source,
                impacted,
                owner_routes,
                direct_rename_allowed=False,
                review_queries=review_queries,
            ),
        }
        files.update(
            {f"query_patches/{query_id}.sql": sql + ";\n" for query_id, sql in patches.items()}
        )
        files["report.html"] = render_evidence_report(
            source_name=source["name"],
            source_field=request.source_field,
            target_field=request.target_field,
            impacted=impacted,
            owner_routes=owner_routes,
            lineage_hops=lineage_hops,
            query_patch_count=len(patches),
            direct_rename_allowed=False,
        )
        return files

    def _render_direct_files(
        self,
        request: ChangeRequest,
        source: dict[str, Any],
        impacted: list[Asset],
        lineage_hops: int,
    ) -> dict[str, str]:
        table = self._quote_qualified(source["name"])
        source_column = self._quote_identifier(request.source_field)
        target_column = self._quote_identifier(request.target_field)
        files = {
            "01_direct.sql": (
                "-- DataHub reported no downstream dependencies for this field.\n"
                f"ALTER TABLE {table} RENAME COLUMN {source_column} TO {target_column};\n"
            ),
            "checks.sql": (
                "-- Confirms that the renamed field is queryable.\n"
                f"SELECT COUNT({target_column}) AS populated_rows FROM {table};\n"
            ),
            "rollback.sql": (
                f"ALTER TABLE {table} RENAME COLUMN {target_column} TO {source_column};\n"
            ),
            "migration-decision.md": self._decision_document(
                request,
                source,
                impacted,
                {},
                direct_rename_allowed=True,
                review_queries=set(),
            ),
        }
        files["report.html"] = render_evidence_report(
            source_name=source["name"],
            source_field=request.source_field,
            target_field=request.target_field,
            impacted=impacted,
            owner_routes={},
            lineage_hops=lineage_hops,
            query_patch_count=0,
            direct_rename_allowed=True,
        )
        return files

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return f'"{value.replace(chr(34), chr(34) * 2)}"'

    @classmethod
    def _quote_qualified(cls, value: str) -> str:
        return ".".join(cls._quote_identifier(part) for part in value.split("."))

    @staticmethod
    def _suffixed_name(value: str, suffix: str) -> str:
        parts = value.split(".")
        parts[-1] += suffix
        return ".".join(parts)

    @staticmethod
    def _safe_field_type(value: str) -> str:
        type_pattern = re.compile(
            r"^[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*)*"
            r"(?:\s*\([0-9,\s]+\))?(?:\[\])?$"
        )
        if not type_pattern.fullmatch(value):
            raise ValueError(f"Unsafe or unsupported field type {value!r}")
        return value

    @staticmethod
    def _owner_routes(impacted: list[Asset]) -> dict[str, list[str]]:
        routes: dict[str, list[str]] = {}
        for asset in impacted:
            for owner in asset.owners or ("unowned",):
                routes.setdefault(owner, []).append(asset.name)
        return {owner: sorted(names) for owner, names in sorted(routes.items())}

    @staticmethod
    def _decision_document(
        request: ChangeRequest,
        source: dict[str, Any],
        impacted: list[Asset],
        owner_routes: dict[str, list[str]],
        *,
        direct_rename_allowed: bool,
        review_queries: set[str],
    ) -> str:
        impact_lines = []
        for asset in impacted:
            owners = ", ".join(f"@{owner}" for owner in asset.owners) or "unowned"
            impact_lines.append(f"- `{asset.name}` — {owners}")
        routes = "\n".join(
            f"- @{owner}: {', '.join(f'`{name}`' for name in names)}"
            for owner, names in owner_routes.items()
        )
        if direct_rename_allowed:
            return (
                f"# Migration decision: `{source['name']}.{request.source_field}`\n\n"
                "## Decision\n\n"
                f"**Direct rename allowed.** DataHub reported no downstream dependencies for "
                f"`{request.source_field}`. Rename it to `{request.target_field}` and verify the "
                "new field before merging.\n\n"
                "## DataHub blast radius\n\nNo downstream assets found.\n\n"
                "## Evidence and controls\n\n"
                "- Run `01_direct.sql`, then run `checks.sql`.\n"
                "- Use `rollback.sql` if validation fails.\n"
            )
        review_note = (
            "\n- Manually review ambiguous qualified queries: "
            + ", ".join(f"`{query_id}`" for query_id in sorted(review_queries))
            + "."
            if review_queries
            else ""
        )
        return (
            f"# Migration decision: `{source['name']}.{request.source_field}`\n\n"
            "## Decision\n\n"
            f"**Direct rename rejected.** Replace `{request.source_field}` with "
            f"`{request.target_field}` through expand, migrate, and contract phases.\n\n"
            "## DataHub blast radius\n\n"
            + ("\n".join(impact_lines) if impact_lines else "No downstream assets found.")
            + "\n\n## Owner routing\n\n"
            + (routes or "- No owners found; assign an owner before contract. ")
            + "\n\n## Evidence and controls\n\n"
            "- Run `01_expand.sql`, then apply the generated query patches.\n"
            "- Run `02_migrate.sql`, dual-write both fields, and require `checks.sql` to "
            "return zero differences.\n"
            "- Obtain owner acknowledgement before `03_contract.sql`.\n"
            "- Use `rollback.sql` before contract if validation fails." + review_note + "\n"
        )


__all__ = ["ChangeRequest", "MigrationBundle", "SchemaFlight", "SnapshotCatalog"]
