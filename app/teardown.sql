-- ============================================================================
-- Chargeback & Dispute Intelligence — teardown.sql
-- ----------------------------------------------------------------------------
-- Removes everything created by app/setup_synthetic.sql or app/setup.sql:
-- the dedicated database (all dispute tables, views, semantic view, agent,
-- reports table) and the dedicated warehouse. Irreversible.
-- ============================================================================

DROP DATABASE IF EXISTS SNOWPACK_DISPUTE_INTEL;
DROP WAREHOUSE IF EXISTS SNOWPACK_DISPUTE_INTEL_WH;
