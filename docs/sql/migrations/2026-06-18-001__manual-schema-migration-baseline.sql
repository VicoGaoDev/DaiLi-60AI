-- Baseline for switching production releases to manual, versioned SQL migrations.
-- Created on 2026-06-18.
--
-- Context:
-- 1. Applications now default to DB_RUN_STARTUP_SCHEMA_SYNC=false.
-- 2. Recent commits did not introduce new schema changes that require manual DDL.
-- 3. This baseline file marks the cutover point for future ordered SQL migrations.
--
-- Execution:
-- Run once in production before adopting the new manual migration workflow.

SELECT
  'baseline: manual schema migration workflow enabled' AS message,
  NOW() AS executed_at;
