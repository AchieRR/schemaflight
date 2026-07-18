# Devpost submission draft

Live validation status: **passed** on release commit [`af4373f`](https://github.com/AchieRR/schemaflight/commit/af4373f1a1609c28aaf5ce3131809f0434e08526) in [public run 29655960989](https://github.com/AchieRR/schemaflight/actions/runs/29655960989), with [durable sanitized evidence](https://github.com/AchieRR/schemaflight/releases/tag/live-validation-af4373f). The entrant authorized preparation and publication of the entry in the operating thread. Eligibility, ownership, permitted-period, and rules attestations must still be answered truthfully from the entrant's actual facts during registration. The public demo is live; registration and the final video are still outstanding.

Status: **authorized draft** — live validation and publication permission are complete; register the entry, validate the required entrant attestations, and finish the public demo video before final submission.

## Listing fields

**Project name:** SchemaFlight

**Tagline:** A blast-radius-aware compiler that turns risky schema renames into DataHub-grounded migration bundles a data team can review and merge.

**Challenge:** Metadata-Aware Code Generation & Development

**DataHub technologies:** DataHub OSS / Core Platform; DataHub Agent Context Kit; DataHub Python SDK and emitter APIs.

**Built with:** Python 3.13, DataHub Core 1.6.0, `datahub-agent-context[langchain]`, DuckDB, SQLGlot, pytest, Ruff, HTML/CSS.

**Repository:** https://github.com/AchieRR/schemaflight

**Try it out:** https://achierr.github.io/schemaflight/examples/ecommerce/generated/report.html

**Demo video:** pending public video URL, under three minutes

## About the project

### Inspiration

A schema rename is rarely local. A developer may see one table and one column while the organization’s metadata graph sees downstream models, dashboards, exports, PII tags, observed queries, and owners. Code generators that miss that context produce migrations that are syntactically plausible and operationally dangerous.

SchemaFlight asks a narrower, practical question: can DataHub context turn a breaking rename into code a real data team would merge?

### What it does

Given a `rename_column` request, SchemaFlight reads live schema, column lineage, ownership, field tags, and recorded query usage through the official DataHub Agent Context Kit. It fails closed when evidence is incomplete, rejects a direct rename when downstream or query usage exists, and emits a deterministic migration bundle:

- expand, migrate, validate, contract, and rollback SQL;
- SQL-AST-based downstream query patches with ambiguity routed to review;
- a machine-readable impact manifest with lineage edges and owners;
- a human migration decision and acknowledgement record; and
- a self-contained evidence report.

The generated lifecycle is executed against DuckDB in tests. SchemaFlight never auto-executes production SQL. Write-back is a separate explicit flag that saves the decision as a DataHub document related to the source dataset.

### How we built it

The compiler core depends on a small catalog protocol. The reproducible adapter reads a committed ecommerce snapshot; the live adapter wraps the official Agent Context Kit tools for entities, schema fields, lineage, and dataset queries. A deterministic breadth-first traversal preserves lineage depth and edges, while strict completeness checks reject truncated live evidence.

Migration SQL uses quoted identifiers and a controlled DuckDB type surface. SQLGlot rewrites only unqualified references in single-source statements; qualified or multi-source ambiguity remains untouched and is listed for human review. Generated artifacts are path-contained, stale managed artifacts are removed safely, and write-back is off by default.

The live seeder uses synchronous DataHub SDK/emitter writes to create a synthetic PII-tagged source, a two-hop lineage graph, owners, and a recorded retention query. This makes the judged flow reproducible without connecting to a private stack.

### Challenges we ran into

The first green implementation still had unsafe edges. Its compatibility view became invalid after contract, non-null divergence escaped validation, dashboards could receive invalid field-lineage calls, pagination could silently truncate evidence, and textual query replacement could rewrite literals or unrelated columns.

Independent review converted those into regression tests. The final lifecycle rebuilds its view, validates with `IS DISTINCT FROM`, treats non-datasets as terminal field impacts, fails closed on inconsistent totals, uses an SQL AST, and distinguishes safe patches from review-required queries.

### Accomplishments

- A full expand/migrate/validate/contract lifecycle that executes in DuckDB.
- Meaningful DataHub usage across schema, multi-hop column lineage, tags, owners, observed queries, and explicit document write-back.
- Deterministic snapshot and live modes behind one compiler interface.
- Fail-closed evidence handling and 26 local tests, plus a pinned official-package CI contract job.
- Checked-in mergeable sample artifacts and a self-contained visual report.
- Two independent review passes with every P1/P2 code finding resolved.
- A public end-to-end DataHub Core v1.6.0 validation with live lineage, PII tag, owners, recorded query, browser evidence, and Decision document write-back/read-back.

### What we learned

Metadata grounding is not just retrieval. A safe code generator needs completeness semantics, explicit trust boundaries, and a decision policy that treats missing context differently from “no impact.” DataHub’s graph becomes most useful when the output also contributes durable context back for the next workflow.

### What’s next

- Add dialect strategies and database-specific dual-write mechanisms.
- Extend the request model beyond column renames.
- Resolve table aliases with DataHub query subjects for more safe AST patches.
- Add pull-request annotations and owner acknowledgement workflows.
- Contribute reusable lineage-completeness and migration-context patterns upstream.

## Judge-facing proof map

| Criterion | Evidence |
| --- | --- |
| Use of DataHub | Live Agent Context reads schema, two-hop lineage, owners, tags, and recorded queries; explicit decision-document write-back. |
| Technical execution | Full DuckDB lifecycle, fail-closed pagination, safe AST rewriting, official-package contract CI, reproducible wheel install. |
| Originality | Compiles metadata evidence into a controlled migration protocol instead of only displaying impact analysis. |
| Real-world usefulness | Produces SQL, tests, patches, rollback, owner routing, and a manifest suitable for code review. |
| Submission quality | Public quickstart, checked-in examples, under-three-minute runbook, and self-contained evidence report. |

## Human pre-submission checklist

- Confirm the entrant is at least 18 / age of majority and resides in an eligible jurisdiction.
- Confirm no employer, client, team, or organization owns or restricts the work.
- Read and accept the binding official rules, releases, publicity license, and verification/tax requirements.
- Confirm all work was created during the permitted submission period and disclose development assistance accurately.
- Complete the live validation checklist and replace every `pending` field with a public, sign-in-free URL.
- Review the public repository for secrets, personal paths, third-party marks, and unsupported claims.
- Verify the video is under three minutes and exactly matches the release commit.
- Save a draft first; submit only after the final human review.
