-- ============================================================================
-- Chargeback & Dispute Intelligence: setup_cfpb.sql (real-data benchmark)
-- ----------------------------------------------------------------------------
-- Run sql/setup.sql first. This script swaps the synthetic complaint benchmark
-- for REAL CFPB consumer complaints about payment-card products, aggregated by
-- month. The dispute book (DISPUTE_FACT) stays synthetic: a processor's own
-- ledger has no public source. Swap DISPUTE_FACT for your own chargeback data
-- (same columns) to go live.
--
-- Prerequisite: the free CFPB complaint data in your account, mounted as a
-- database named CFPB_COMPLAINT (for example from a free Snowflake Marketplace
-- listing of CFPB consumer complaints). Change the database name below if yours
-- differs. The disputes are joined to complaints BY MONTH ONLY (no foreign key);
-- complaint counts are a market-wide, non-additive signal.
-- ============================================================================
USE ROLE ACCOUNTADMIN;
GRANT IMPORTED PRIVILEGES ON DATABASE CFPB_COMPLAINT TO ROLE SNOWPACK_DISPUTE_INTEL_ROLE;

USE ROLE SNOWPACK_DISPUTE_INTEL_ROLE;
USE WAREHOUSE SNOWPACK_DISPUTE_INTEL_WH;
USE SCHEMA SNOWPACK_DISPUTE_INTEL.CORE;

-- Type-switch safety: DISPUTE_CFPB_BENCHMARK is a TABLE in setup.sql and a VIEW in
-- setup_cfpb.sql. DROP VIEW fails on a table (and vice versa), so try both quietly.
EXECUTE IMMEDIATE $$
BEGIN
  BEGIN DROP VIEW IF EXISTS DISPUTE_CFPB_BENCHMARK; EXCEPTION WHEN OTHER THEN NULL; END;
  BEGIN DROP TABLE IF EXISTS DISPUTE_CFPB_BENCHMARK; EXCEPTION WHEN OTHER THEN NULL; END;
END;
$$;
CREATE OR REPLACE VIEW DISPUTE_CFPB_BENCHMARK
  COMMENT = 'REAL CFPB consumer complaints for payment-card products, aggregated monthly.'
AS
SELECT LAST_DAY(DATE_RECEIVED) AS month_end,
       COUNT(*) AS cfpb_complaint_count,
       ROUND(AVG(IFF(COMPANY_RESPONSE_TO_CONSUMER = 'Closed with monetary relief', 1, 0)) * 100, 1) AS cfpb_pct_monetary_relief,
       ROUND(AVG(IFF(TIMELY_RESPONSE, 1, 0)) * 100, 1) AS cfpb_pct_timely_response,
       ROUND(AVG(IFF(CONSUMER_DISPUTED = 'Yes', 1, 0)) * 100, 1) AS cfpb_pct_consumer_disputed
FROM CFPB_COMPLAINT.DERIVED.CFPB_COMPLAINT_MAPPED
WHERE PRODUCT IN ('Credit card', 'Credit card or prepaid card', 'Money transfer, virtual currency, or money service', 'Prepaid card')
  AND DATE_RECEIVED BETWEEN '2024-07-01' AND '2026-06-30'
GROUP BY 1;

CREATE OR REPLACE VIEW DISPUTE_DATA_SOURCE_INFO AS
SELECT 'marketplace' AS mode,
       'Synthetic dispute book benchmarked against REAL CFPB consumer complaints for payment-card products (monthly, non-additive).' AS note;

SELECT COUNT(*) AS cfpb_months FROM DISPUTE_CFPB_BENCHMARK;
