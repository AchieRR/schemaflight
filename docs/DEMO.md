# SchemaFlight three-minute demo

Target length: **2:45**. Record only after the live DataHub checklist passes. Keep the terminal at a readable font size and hide tokens, browser profiles, notifications, and unrelated tabs.

## Pre-recording state

- DataHub v1.6.0 is running locally and bound only to the local machine.
- The demo graph has been seeded with `schemaflight seed-datahub`.
- `build/live-demo` does not exist or is empty.
- The repository is on the public release commit and all tests pass.
- The report and DataHub UI are already open in separate, clean browser tabs.

## Shot list and narration

### 0:00–0:18 — The failure mode

Show `examples/ecommerce/rename-email.json`, then the source schema in DataHub.

> “Renaming a column looks like a one-line migration. But `shop.customer.email` carries a PII tag, feeds a customer model, and reaches a retention consumer two hops away. A code generator that sees only the edited file will break them.”

### 0:18–0:42 — Ground the decision in DataHub

Show the live DataHub lineage graph and owners for the source, model, and consumer.

> “SchemaFlight reads the live schema, field lineage, ownership, and recorded query context through DataHub’s Agent Context Kit. The safety decision is deterministic: incomplete evidence fails closed, and downstream usage rejects the direct rename.”

### 0:42–1:05 — Compile the bundle

Run:

```console
python -m schemaflight compile --datahub-server http://localhost:8080 --request examples/ecommerce/rename-email.json --output build/live-demo
```

Pause on the JSON summary showing high risk and `direct_rename_allowed: false`.

> “The compiler returns a machine-readable verdict and creates a controlled expand, migrate, validate, and contract bundle. It does not execute production SQL.”

### 1:05–1:38 — Make the blast radius legible

Open `build/live-demo/report.html`. Point to hop count, impacted assets, owner routes, and the flight plan.

> “The self-contained report makes the evidence reviewable without a running frontend. Every owner and affected asset came from DataHub; no model invented this graph.”

### 1:38–2:08 — Show mergeable artifacts and executable proof

Show `01_expand.sql`, `checks.sql`, the query patch, and `impact-manifest.json`. Then run:

```console
python -m pytest tests/test_compile_rename.py -q
```

> “The bundle adds and backfills the new field, requires dual writes, detects null and non-null divergence, rebuilds its compatibility view before contract, and preserves rollback. The full lifecycle executes against DuckDB, while SQLGlot rewrites only safe query references and flags ambiguity for review.”

### 2:08–2:34 — Write context back

Run the local-only write-back:

```console
python -m schemaflight compile --datahub-server http://localhost:8080 --request examples/ecommerce/rename-email.json --output build/live-demo --write-back
```

Open the resulting decision document in DataHub.

> “Write-back is an explicit opt-in. The migration decision is saved as a DataHub document related to the source dataset, so the next person or agent inherits the decision and controls.”

### 2:34–2:45 — Close

Return to the report hero.

> “SchemaFlight turns a risky rename into evidence-linked code a data team can actually review and merge: context to decision, decision to migration, migration back to context.”

## Recording acceptance checks

- Total runtime is below three minutes.
- The video shows a real DataHub instance, not only fixtures or mocks.
- The terminal output, lineage, report, tests, and write-back are readable at normal playback speed.
- No credential, local username, private address, notification, or unrelated browser content is visible.
- Captions match the final narration and the video is publicly viewable without sign-in.
- Every claim shown in the video is reproduced by the release commit.
