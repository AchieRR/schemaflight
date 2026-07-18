-- Expand: keep "email" authoritative while adding "primary_email".
ALTER TABLE "shop"."customer" ADD COLUMN "primary_email" VARCHAR;
UPDATE "shop"."customer" SET "primary_email" = "email"
WHERE "primary_email" IS NULL;
CREATE OR REPLACE VIEW "shop"."customer_compat" AS SELECT * FROM "shop"."customer";
