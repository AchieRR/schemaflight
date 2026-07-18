-- Safe before the contract phase; the original column remains authoritative.
DROP VIEW IF EXISTS "shop"."customer_compat";
ALTER TABLE "shop"."customer" DROP COLUMN "primary_email";
CREATE OR REPLACE VIEW "shop"."customer_compat" AS SELECT * FROM "shop"."customer";
-- After contract, restore from a verified backup before dropping the new column.
