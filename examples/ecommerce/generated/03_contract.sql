-- Run only after every manifest dependency has migrated.
DROP VIEW IF EXISTS "shop"."customer_compat";
ALTER TABLE "shop"."customer" DROP COLUMN "email";
CREATE OR REPLACE VIEW "shop"."customer_compat" AS SELECT * FROM "shop"."customer";
