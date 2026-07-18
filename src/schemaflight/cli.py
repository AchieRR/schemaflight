from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from schemaflight import ChangeRequest, SchemaFlight, SnapshotCatalog
from schemaflight.datahub_catalog import AgentContextCatalog
from schemaflight.demo_datahub import seed_demo_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schemaflight",
        description="Compile lineage-aware schema migration bundles.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile", help="Compile one change request.")
    catalog_group = compile_parser.add_mutually_exclusive_group(required=True)
    catalog_group.add_argument("--catalog", type=Path, help="Reproducible catalog snapshot.")
    catalog_group.add_argument("--datahub-server", help="Live DataHub GMS base URL.")
    compile_parser.add_argument("--request", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    compile_parser.add_argument(
        "--write-back",
        action="store_true",
        help="Publish the generated decision document to the live DataHub instance.",
    )
    seed_parser = subparsers.add_parser(
        "seed-datahub",
        help="Upsert the deterministic ecommerce demo graph into DataHub.",
    )
    seed_parser.add_argument("--datahub-server", required=True, help="Live DataHub GMS base URL.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compile":
        if args.catalog:
            if args.write_back:
                raise SystemExit("--write-back requires --datahub-server")
            catalog = SnapshotCatalog.from_file(args.catalog)
        else:
            catalog = AgentContextCatalog.connect(
                server=args.datahub_server,
                token=os.environ.get("DATAHUB_GMS_TOKEN"),
                include_mutations=args.write_back,
            )
        request = ChangeRequest.from_file(args.request)
        bundle = SchemaFlight(catalog).compile(request)
        destination = bundle.write_to(args.output)
        summary = {
            "assets_impacted": len(bundle.blast_radius.assets),
            "direct_rename_allowed": bundle.risk.direct_rename_allowed,
            "output": str(destination),
            "risk": bundle.risk.level,
        }
        if args.write_back:
            source = catalog.asset(request.dataset_urn)
            summary["decision_document_urn"] = catalog.publish_decision(
                source_urn=request.dataset_urn,
                source_name=source["name"],
                source_field=request.source_field,
                target_field=request.target_field,
                content=bundle.files["migration-decision.md"],
            )
        print(json.dumps(summary, sort_keys=True))
        return 0
    if args.command == "seed-datahub":
        summary = seed_demo_catalog(
            server=args.datahub_server,
            token=os.environ.get("DATAHUB_GMS_TOKEN"),
        )
        print(json.dumps(summary, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command {args.command!r}")
