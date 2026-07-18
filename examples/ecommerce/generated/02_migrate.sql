-- Migrate readers, apply query patches, and dual-write both fields.
UPDATE "shop"."customer" SET "primary_email" = "email"
WHERE "primary_email" IS NULL;
