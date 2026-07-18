# Live DataHub validation checklist

This checklist is intentionally separate from the snapshot demo. Do not mark the submission end-to-end until every item is captured from a real DataHub Core instance.

## Prerequisites

- A human-approved container runtime with acceptable license and Windows subsystem changes.
- At least 2 CPUs, 8 GB RAM, 13 GB free disk, and a local-only development environment.
- Python 3.11–3.13 with `.[dev,datahub]` installed.
- No production DataHub URL or production token in the shell history.

## Start and seed

```console
datahub docker quickstart --version v1.6.0
python -m schemaflight seed-datahub --datahub-server http://localhost:8080
```

Required evidence:

- DataHub UI responds at `http://localhost:9002`.
- GMS responds at `http://localhost:8080`.
- Seed summary reports three datasets and one query.
- DataHub shows `shop.customer`, `analytics.customer_360`, and `growth.retention_export`.
- `email` has a PII tag; the model and consumer have their expected owners.
- Column lineage reaches the model and consumer in two hops.
- The recorded retention query is attached to `analytics.customer_360`.

## Read-only compile

```console
python -m schemaflight compile --datahub-server http://localhost:8080 --request examples/ecommerce/rename-email.json --output build/live-demo
```

Required evidence:

- Exit code is zero.
- Risk is `high` and direct rename is rejected.
- Two assets and two lineage hops are reported.
- A query patch for `retention-export` is present.
- `impact-manifest.json` contains live URNs, owner routes, lineage edges, and no incomplete-evidence warning.
- `report.html` renders with no remote requests or console errors.

## Explicit write-back

Use only the local synthetic graph.

```console
python -m schemaflight compile --datahub-server http://localhost:8080 --request examples/ecommerce/rename-email.json --output build/live-demo --write-back
```

Required evidence:

- Output contains a DataHub document URN.
- The decision document exists in DataHub, relates to `shop.customer`, and contains the staged controls.
- A read-only compile does not create a document.

## Regression and capture

```console
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Capture a sanitized transcript and screenshots of the live lineage, generated report, and decision document. Record DataHub, Agent Context Kit, and repository versions. Never commit tokens, local DataHub state, Docker volumes, or screenshots containing personal information.

## Result record

- Date/time (UTC): pending
- Release commit: pending
- DataHub version: pending
- Agent Context Kit version: pending
- Container runtime/version: pending human approval
- Read-only compile: pending
- Query patch observed: pending
- Write-back document URN: pending
- Full regression: pending
- Reviewer: pending
