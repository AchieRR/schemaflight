# Migration decision: `shop.customer.email`

## Decision

**Direct rename rejected.** Replace `email` with `primary_email` through expand, migrate, and contract phases.

## DataHub blast radius

- `analytics.customer_360` — @analytics
- `retention_dashboard` — @growth

## Owner routing

- @analytics: `analytics.customer_360`
- @growth: `retention_dashboard`

## Evidence and controls

- Run `01_expand.sql`, then apply the generated query patches.
- Run `02_migrate.sql`, dual-write both fields, and require `checks.sql` to return zero differences.
- Obtain owner acknowledgement before `03_contract.sql`.
- Use `rollback.sql` before contract if validation fails.
