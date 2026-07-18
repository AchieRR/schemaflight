# Product requirements: SchemaFlight

## Problem

A schema rename that looks local can break transformations, dashboards, and downstream consumers. Code generators usually see only the edited file, so they generate destructive SQL without ownership, usage, or lineage context.

## Public behavior

Given a rename request and a catalog adapter, SchemaFlight must:

1. read the source schema and field-level, multi-hop downstream context;
2. classify a direct rename as unsafe when downstream dependencies exist;
3. generate a staged compatibility migration, backfill, checks, query patches, rollout, rollback, and a machine-readable impact manifest;
4. preserve evidence linking every decision to catalog context; and
5. optionally publish a decision document back through a live DataHub adapter.

## First vertical slice

For the synthetic ecommerce catalog, renaming `customer.email` to `primary_email` must discover the `customer_360` model and `retention_dashboard`, generate a compatibility phase, and patch the recorded downstream query without modifying the snapshot.

## Non-goals for the MVP

- Executing changes against production systems.
- Claiming that generated SQL is portable across every database.
- Using an LLM for graph traversal or safety decisions.
- Treating a snapshot demo as a substitute for the required live DataHub integration.

## Success evidence

- Public integration tests exercise compiler behavior through its public interface.
- Generated SQL executes against the included DuckDB demo.
- A live DataHub quickstart demo shows metadata read and decision-document write-back.
- The repository is Apache-2.0 licensed and includes reproducible setup instructions.
