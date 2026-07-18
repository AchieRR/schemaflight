-- Must return zero before the contract phase.
SELECT COUNT(*) AS unmigrated_rows FROM "shop"."customer"
WHERE "primary_email" IS DISTINCT FROM "email";
