# Live DataHub validation checklist

This checklist is intentionally separate from the snapshot demo. The automated live checks were completed against a fresh DataHub Core instance on 2026-07-18; the public run and sanitized evidence are linked in the result record.

## Prerequisites

- An authorized container runtime. The validated run used Docker Engine on a public GitHub-hosted runner; local Podman remains an optional development path.
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

- Date/time (UTC): 2026-07-18 18:33:39
- Public validation run: [GitHub Actions run 29655960989](https://github.com/AchieRR/schemaflight/actions/runs/29655960989) — success
- Durable sanitized evidence: [GitHub release `live-validation-af4373f`](https://github.com/AchieRR/schemaflight/releases/tag/live-validation-af4373f)
- Release commit: [`af4373f1a1609c28aaf5ce3131809f0434e08526`](https://github.com/AchieRR/schemaflight/commit/af4373f1a1609c28aaf5ce3131809f0434e08526)
- DataHub version: Core/GMS `v1.6.0`; CLI `1.6.0.6`
- Agent Context Kit version: `1.6.0.13`
- Container runtime/version: Docker Engine `28.0.4`; Docker Compose `2.38.2`; GitHub-hosted Ubuntu runner
- Indexed source evidence: `shop.customer.email` with `PII`; exact two-hop field lineage ready
- Read-only compile: passed — high risk, direct rename rejected, two impacted assets
- Browser validation: passed in Chrome `150.0.7871.114` — zero console errors and zero external requests
- Query patch observed: `query_patches/retention-export.sql`
- Write-back/read-back: passed — published Decision document related to `shop.customer`
- Ephemeral Decision URN: `urn:li:document:shared-3caa2aa4-e0ed-4681-846a-e7ae90fa92de`
- Determinism: all nine read-only and write-back artifacts were byte-identical
- Full regression: 26 tests passed; Ruff check and format passed
- Independent reviewer: GO — no actionable P1/P2 findings

The document URN and local DataHub instance were ephemeral by design. The workflow artifact expires after 14 days; the durable GitHub release preserves the sanitized exact readback, live manifest, browser audit, versions, runner capacity, summaries, and screenshot without retaining credentials or container state. The public report preserves the generated visual experience, while the successful workflow logs preserve all step outcomes.
