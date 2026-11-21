-- ============================================================================
-- Chargeback & Dispute Intelligence: setup.sql (synthetic, no listing needed)
-- ----------------------------------------------------------------------------
-- Chargeback / dispute intelligence for a card payments processor. A synthetic
-- dispute book (network / reason code / merchant category / month, with a
-- holiday chargeback spike) is benchmarked against a monthly consumer-complaint
-- signal. Here the complaint benchmark is SYNTHETIC too; sql/setup_cfpb.sql
-- swaps in REAL CFPB payment-card complaints.
--
-- Synthetic data and illustrative logic only. Not production, regulatory or
-- compliance advice. Run top to bottom in a Snowsight SQL worksheet; no edits.
-- Takes about 1 minute on an XSMALL warehouse.
--
-- Requires: ACCOUNTADMIN (or USERADMIN + SECURITYADMIN) and SYSADMIN, and Cortex
-- AI (AI_COMPLETE, Cortex Agents, Cortex Analyst) in your region or with
-- cross-region inference enabled.
--
-- Creates (sql/cleanup.sql drops all of it); changes nothing that already exists:
--   role       SNOWPACK_DISPUTE_INTEL_ROLE  least-privilege role for setup + app
--   warehouse  SNOWPACK_DISPUTE_INTEL_WH    XSMALL, AUTO_SUSPEND = 60
--   database   SNOWPACK_DISPUTE_INTEL       schema CORE (prefix DISPUTE_):
--     DISPUTE_CATEGORY, DISPUTE_REASON_CODE, DISPUTE_MERCHANT (dims),
--     DISPUTE_FACT (9,960 synthetic disputes), DISPUTE_CFPB_BENCHMARK,
--     DISPUTE_BENCHMARK (wide view), DISPUTE_DATA_SOURCE_INFO, DISPUTE_SV
--     (semantic view), DISPUTE_REPORTS, DISPUTE_AGENT (Cortex Agent),
--     stage DISPUTE_APP_STAGE (for the Streamlit app files)
--
-- Determinism: every random value is UNIFORM(lo, hi, HASH(<row key>, <salt>)),
-- so re-running gives identical rows (checked with HASH_AGG; see data/README.md).
-- ============================================================================

-- 0. Least-privilege role ------------------------------------------------------
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS SNOWPACK_DISPUTE_INTEL_ROLE
  COMMENT = 'Chargeback & Dispute Intelligence example: owns only objects in SNOWPACK_DISPUTE_INTEL';
GRANT ROLE SNOWPACK_DISPUTE_INTEL_ROLE TO ROLE SYSADMIN;
SET my_user = CURRENT_USER();
GRANT ROLE SNOWPACK_DISPUTE_INTEL_ROLE TO USER IDENTIFIER($my_user);
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SNOWPACK_DISPUTE_INTEL_ROLE; -- AI_COMPLETE, Agents, Analyst

-- 1. Warehouse, database, schema (SYSADMIN) with schema-scoped grants ----------
USE ROLE SYSADMIN;
CREATE WAREHOUSE IF NOT EXISTS SNOWPACK_DISPUTE_INTEL_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Chargeback & Dispute Intelligence example';
CREATE DATABASE IF NOT EXISTS SNOWPACK_DISPUTE_INTEL COMMENT = 'Chargeback & Dispute Intelligence example (synthetic data)';
CREATE SCHEMA IF NOT EXISTS SNOWPACK_DISPUTE_INTEL.CORE
  COMMENT = 'Chargeback & Dispute Intelligence: card dispute / chargeback benchmarking';
GRANT USAGE, OPERATE ON WAREHOUSE SNOWPACK_DISPUTE_INTEL_WH TO ROLE SNOWPACK_DISPUTE_INTEL_ROLE;
GRANT USAGE ON DATABASE SNOWPACK_DISPUTE_INTEL TO ROLE SNOWPACK_DISPUTE_INTEL_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE SEMANTIC VIEW, CREATE AGENT, CREATE STAGE, CREATE STREAMLIT
  ON SCHEMA SNOWPACK_DISPUTE_INTEL.CORE TO ROLE SNOWPACK_DISPUTE_INTEL_ROLE;

-- Everything below runs as the pack role, so it owns only what it creates.
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

-- 2. Merchant-category dim + chargeback-rate driver -----------------------------
CREATE OR REPLACE TABLE DISPUTE_CATEGORY (
  merchant_category STRING, category_name STRING, base_cb_bps FLOAT, base_txn INT
);
INSERT INTO DISPUTE_CATEGORY VALUES
  ('RETAIL','Retail & E-commerce',   42,  900000),
  ('TRAVEL','Travel & Hospitality',  65,  300000),
  ('DIGITAL','Digital Goods & Subscriptions', 120, 600000),
  ('GROCERY','Grocery & Essentials', 30,  500000);

-- 3. Dispute reason-code dim (Visa dotted + Mastercard 4-digit) ----------------
CREATE OR REPLACE TABLE DISPUTE_REASON_CODE (
  reason_code STRING, network STRING, reason_category STRING, reason_name STRING,
  description STRING, typical_root_cause STRING, is_friendly_fraud BOOLEAN, weight FLOAT
);
INSERT INTO DISPUTE_REASON_CODE VALUES
  ('10.4','VISA','Fraud','Card-Absent / Friendly Fraud','Cardholder claims they did not authorize a card-not-present charge','Friendly fraud / first-party misuse', TRUE, 0.30),
  ('13.1','VISA','Consumer Disputes','Merchandise Not Received','Goods or services not received by the promised date','Fulfillment / delivery failure', FALSE, 0.22),
  ('13.2','VISA','Consumer Disputes','Cancelled Recurring','Charge after a recurring subscription was cancelled','Cancellation-flow / billing defect', FALSE, 0.14),
  ('13.3','VISA','Consumer Disputes','Not As Described','Goods differ materially from the description','Product description / quality', FALSE, 0.12),
  ('12.6','VISA','Processing Errors','Duplicate / Paid Other Means','Transaction billed twice or already paid another way','Processing / terminal error', FALSE, 0.07),
  ('4853','MASTERCARD','Consumer Disputes','Cardholder Dispute','General cardholder dispute of goods/services','Fulfillment / description', FALSE, 0.10),
  ('4837','MASTERCARD','Fraud','No Cardholder Authorization','Cardholder denies authorizing the transaction','Fraud / friendly fraud', TRUE, 0.05);

-- 4. Merchant dim (4 merchants per category; coined, fictional names) ---------
CREATE OR REPLACE TABLE DISPUTE_MERCHANT (
  merchant_id INT, merchant_name STRING, mcc STRING, merchant_category STRING, merchant_seq INT
);
INSERT INTO DISPUTE_MERCHANT VALUES
  (101,'Quenfield Outfitters','5651','RETAIL',1),(102,'Marrowby Home','5732','RETAIL',2),(103,'Tessaly Market','5311','RETAIL',3),(104,'Orvane Apparel','5651','RETAIL',4),
  (201,'Skerrow Travel','4722','TRAVEL',1),(202,'Vellmar Resorts','7011','TRAVEL',2),(203,'Aerquill Air','3000','TRAVEL',3),(204,'Dorrowby Tours','4722','TRAVEL',4),
  (301,'Strevix Stream','5815','DIGITAL',1),(302,'Plunvault Games','5816','DIGITAL',2),(303,'Cindrel Cloud','5817','DIGITAL',3),(304,'Moxquin Play','5816','DIGITAL',4),
  (401,'Fennick Grocer','5411','GROCERY',1),(402,'Pallowmere Market','5411','GROCERY',2),(403,'Quillby Pantry','5499','GROCERY',3),(404,'Thressa Foods','5411','GROCERY',4);

-- 24 month-ends ending 2026-06-30 (the as-of date), holiday factor for Nov/Dec/Jan
CREATE OR REPLACE TEMP TABLE DISPUTE_MONTHS AS
SELECT LAST_DAY(DATEADD(month, SEQ4(), '2024-07-01'::date)) AS month_end, SEQ4() AS m_idx,
       (CASE WHEN MONTH(LAST_DAY(DATEADD(month, SEQ4(), '2024-07-01'::date))) IN (11,12,1) THEN 1.6 ELSE 1.0 END) AS holiday_f
FROM TABLE(GENERATOR(ROWCOUNT => 24));

-- 5. Synthetic per-dispute fact -------------------------------------------------
-- cell = (category, reason_code, network, month); target_count drives how many
-- individual disputes are generated (holiday-skewed). Status depends on age:
-- recent disputes are still open or in pre-arbitration, older ones are resolved.
CREATE OR REPLACE TEMP TABLE DISPUTE_CELLS AS
SELECT c.merchant_category, r.reason_code, r.network, r.is_friendly_fraud, m.month_end, m.m_idx, m.holiday_f,
       LEAST(600, GREATEST(2, ROUND(c.base_txn*(c.base_cb_bps/10000.0)*r.weight*m.holiday_f/40.0))) AS target_count
FROM DISPUTE_CATEGORY c CROSS JOIN DISPUTE_REASON_CODE r CROSS JOIN DISPUTE_MONTHS m;

CREATE OR REPLACE TEMP TABLE DISPUTE_NUMS AS
SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1 AS n FROM TABLE(GENERATOR(ROWCOUNT => 600));

CREATE OR REPLACE TABLE DISPUTE_FACT
  COMMENT = 'SYNTHETIC per-dispute chargeback fact (network/reason/category/month), holiday-skewed, hash-seeded.'
AS
WITH base AS (
  SELECT cl.*, nm.n,
         HASH(cl.merchant_category, cl.reason_code, cl.month_end, nm.n) AS k,
         23 - cl.m_idx AS age_months
  FROM DISPUTE_CELLS cl
  JOIN DISPUTE_NUMS nm ON nm.n < cl.target_count
), drawn AS (
  SELECT b.*,
         ROUND(UNIFORM(2500, 120000, HASH(k, 202)) / 100.0, 2) AS amt,
         UNIFORM(0, 99, HASH(k, 204)) AS u_open,
         UNIFORM(0, 99, HASH(k, 205)) AS u_prearb,
         UNIFORM(0, 99, HASH(k, 206)) AS u_win,
         -- Planted story: one subscription merchant carries most Digital 13.2 disputes.
         IFF(merchant_category = 'DIGITAL' AND reason_code = '13.2' AND UNIFORM(0, 99, HASH(k, 207)) < 60,
             1, MOD(n, 4) + 1) AS merchant_seq
  FROM base b
)
SELECT ROW_NUMBER() OVER (ORDER BY d.month_end, d.merchant_category, d.network, d.reason_code, d.n) AS dispute_id,
       2000000000 + ROW_NUMBER() OVER (ORDER BY d.month_end, d.merchant_category, d.network, d.reason_code, d.n) AS transaction_id,
       mm.merchant_id, mm.merchant_name, d.merchant_category, d.reason_code, d.network,
       DATEADD(day, UNIFORM(0, 27, HASH(d.k, 101)), DATE_TRUNC('month', d.month_end))::date AS date_filed,
       d.month_end,
       d.amt AS dispute_amount,
       ROUND(d.amt * (1 + UNIFORM(0, 60, HASH(d.k, 203)) / 100.0), 2) AS transaction_amount,
       d.is_friendly_fraud,
       CASE WHEN d.age_months <= 1 AND d.u_open < 40 THEN 'open'
            WHEN d.age_months <= 3 AND d.u_open < 8  THEN 'open'
            WHEN d.age_months <= 1 AND d.u_prearb < 12 THEN 'pre-arb'
            WHEN d.age_months <= 3 AND d.u_prearb < 14 THEN 'pre-arb'
            WHEN d.u_win < (CASE WHEN d.is_friendly_fraud THEN 35 ELSE 55 END) THEN 'won'
            ELSE 'lost' END AS status
FROM drawn d
JOIN DISPUTE_MERCHANT mm ON mm.merchant_category = d.merchant_category AND mm.merchant_seq = d.merchant_seq;

ALTER TABLE DISPUTE_FACT ADD COLUMN respond_by DATE;
UPDATE DISPUTE_FACT SET respond_by = DATEADD(day, 30, date_filed) WHERE status IN ('open', 'pre-arb');

-- 6. Complaint benchmark: SYNTHETIC here (REAL CFPB view in setup_cfpb.sql) ----
CREATE OR REPLACE TABLE DISPUTE_CFPB_BENCHMARK
  COMMENT = 'SYNTHETIC consumer-complaint benchmark by month. setup_cfpb.sql replaces this with REAL CFPB payment-card complaints.'
AS
SELECT month_end,
       ROUND(4000 + UNIFORM(0, 1500, HASH(month_end, 301)) + (CASE WHEN MONTH(month_end) IN (11,12,1) THEN 900 ELSE 0 END)) AS cfpb_complaint_count,
       ROUND(12 + UNIFORM(0, 60, HASH(month_end, 302)) / 10.0, 1) AS cfpb_pct_monetary_relief,
       ROUND(97 + UNIFORM(0, 20, HASH(month_end, 303)) / 10.0, 1) AS cfpb_pct_timely_response,
       ROUND(3  + UNIFORM(0, 30, HASH(month_end, 304)) / 10.0, 1) AS cfpb_pct_consumer_disputed
FROM DISPUTE_MONTHS;

-- 7. Wide benchmark view: pre-aggregate the fact to (category, network, reason,
--    month), derive processed-txn + rates, broadcast the MONTHLY complaint
--    benchmark. Complaint columns are NON-ADDITIVE (MAX/AVG in the SV, never SUM).
CREATE OR REPLACE VIEW DISPUTE_BENCHMARK
  COMMENT = 'Dispute book pre-aggregated to (merchant_category, network, reason_code, month) with chargeback/win/friendly-fraud rates and a monthly consumer-complaint benchmark (non-additive).'
AS
WITH f AS (
  SELECT merchant_category, network, reason_code, month_end,
         COUNT(*) AS dispute_count,
         SUM(dispute_amount) AS total_dispute_amount,
         SUM(transaction_amount) AS total_transaction_amount,
         SUM(IFF(status = 'won', 1, 0)) AS won_count,
         SUM(IFF(status IN ('won','lost'), 1, 0)) AS resolved_count,
         SUM(IFF(status = 'lost', dispute_amount, 0)) AS lost_amount,
         SUM(IFF(is_friendly_fraud, 1, 0)) AS friendly_fraud_count
  FROM DISPUTE_FACT GROUP BY 1,2,3,4
),
-- Processed volume per category-month: the category's base volume (scaled to the
-- dispute sample), +25% in Nov-Jan and +1% a month of growth. Disputes rise 60% in
-- the holidays, so the chargeback RATE rises too, by about 28%.
cm AS (
  SELECT DISTINCT f.merchant_category, f.month_end,
         ROUND(c.base_txn / 40.0
               * IFF(MONTH(f.month_end) IN (11,12,1), 1.25, 1.0)
               * (1 + 0.01 * DATEDIFF(month, '2024-07-31'::date, f.month_end))) AS processed_txn_count
  FROM f JOIN DISPUTE_CATEGORY c USING (merchant_category)
)
SELECT f.merchant_category, cat.category_name, f.network, f.reason_code,
       rc.reason_category, rc.reason_name, rc.is_friendly_fraud,
       f.month_end, YEAR(f.month_end) AS report_year, QUARTER(f.month_end) AS report_quarter,
       f.dispute_count, f.total_dispute_amount, f.total_transaction_amount,
       f.won_count, f.resolved_count, f.lost_amount, f.friendly_fraud_count,
       cm.processed_txn_count,
       ROUND(f.dispute_count / NULLIF(cm.processed_txn_count, 0) * 10000, 2) AS chargeback_rate_bps,
       ROUND(f.won_count / NULLIF(f.resolved_count, 0), 3) AS win_rate,
       ROUND(f.friendly_fraud_count / NULLIF(f.dispute_count, 0), 3) AS friendly_fraud_rate,
       b.cfpb_complaint_count, b.cfpb_pct_monetary_relief, b.cfpb_pct_timely_response, b.cfpb_pct_consumer_disputed
FROM f
JOIN DISPUTE_REASON_CODE rc ON rc.reason_code = f.reason_code AND rc.network = f.network
JOIN DISPUTE_CATEGORY cat ON cat.merchant_category = f.merchant_category
JOIN cm ON cm.merchant_category = f.merchant_category AND cm.month_end = f.month_end
LEFT JOIN DISPUTE_CFPB_BENCHMARK b ON b.month_end = f.month_end;

-- 8. Data-source marker (read by the app and the notebook) ---------------------
CREATE OR REPLACE VIEW DISPUTE_DATA_SOURCE_INFO AS
SELECT 'synthetic' AS mode,
       'Synthetic dispute book and synthetic complaint benchmark (no Marketplace listing required). Run sql/setup_cfpb.sql to benchmark the synthetic book against REAL CFPB consumer complaints for payment-card products.' AS note;

-- 9. Semantic view (single wide view; composite PK = true grain) ---------------
CREATE OR REPLACE SEMANTIC VIEW DISPUTE_SV
  TABLES ( d AS SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_BENCHMARK PRIMARY KEY (merchant_category, network, reason_code, month_end)
           WITH SYNONYMS = ('disputes','chargebacks','dispute benchmark')
           COMMENT = 'Card disputes by merchant category, network, reason code and month, with a monthly consumer-complaint benchmark' )
  FACTS (
    d.dispute_count AS DISPUTE_COUNT,
    d.total_dispute_amount AS TOTAL_DISPUTE_AMOUNT,
    d.total_transaction_amount AS TOTAL_TRANSACTION_AMOUNT,
    d.won_count AS WON_COUNT,
    d.resolved_count AS RESOLVED_COUNT,
    d.lost_amount AS LOST_AMOUNT,
    d.friendly_fraud_count AS FRIENDLY_FRAUD_COUNT,
    d.processed_txn_count AS PROCESSED_TXN_COUNT,
    d.chargeback_rate_bps AS CHARGEBACK_RATE_BPS,
    d.win_rate AS WIN_RATE,
    d.friendly_fraud_rate AS FRIENDLY_FRAUD_RATE,
    d.cfpb_complaint_count AS CFPB_COMPLAINT_COUNT,
    d.cfpb_pct_monetary_relief AS CFPB_PCT_MONETARY_RELIEF,
    d.cfpb_pct_timely_response AS CFPB_PCT_TIMELY_RESPONSE,
    d.cfpb_pct_consumer_disputed AS CFPB_PCT_CONSUMER_DISPUTED
  )
  DIMENSIONS (
    d.category_name AS CATEGORY_NAME WITH SYNONYMS = ('merchant category','vertical','segment') COMMENT = 'Merchant category',
    d.merchant_category AS MERCHANT_CATEGORY,
    d.network AS NETWORK WITH SYNONYMS = ('card network','scheme'),
    d.reason_code AS REASON_CODE WITH SYNONYMS = ('chargeback reason','dispute code'),
    d.reason_category AS REASON_CATEGORY WITH SYNONYMS = ('reason group','dispute category'),
    d.reason_name AS REASON_NAME,
    d.is_friendly_fraud AS IS_FRIENDLY_FRAUD WITH SYNONYMS = ('first-party fraud','friendly fraud flag'),
    d.month_end AS MONTH_END WITH SYNONYMS = ('month','period','as of'),
    d.report_year AS REPORT_YEAR WITH SYNONYMS = ('year'),
    d.report_quarter AS REPORT_QUARTER WITH SYNONYMS = ('quarter')
  )
  METRICS (
    d.total_disputes AS SUM(d.dispute_count) COMMENT = 'Total disputes/chargebacks',
    d.total_dispute_usd AS SUM(d.total_dispute_amount) COMMENT = 'Total disputed amount (USD)',
    d.total_txn_usd AS SUM(d.total_transaction_amount) COMMENT = 'Total underlying transaction amount (USD)',
    d.total_won AS SUM(d.won_count) COMMENT = 'Disputes won',
    d.total_resolved AS SUM(d.resolved_count) COMMENT = 'Disputes resolved (won+lost); overall win rate = total_won / total_resolved',
    d.total_lost_usd AS SUM(d.lost_amount) COMMENT = 'Disputed dollars lost (status lost)',
    d.total_friendly_fraud AS SUM(d.friendly_fraud_count) COMMENT = 'Friendly-fraud disputes',
    d.processed_txn AS MAX(d.processed_txn_count) COMMENT = 'Processed transactions for a merchant category in a month (non-additive across reason codes; group by MERCHANT_CATEGORY and MONTH_END, then sum)',
    d.avg_chargeback_rate_bps AS AVG(d.chargeback_rate_bps) COMMENT = 'Average chargeback rate (bps of processed txns)',
    d.avg_win_rate AS AVG(d.win_rate) COMMENT = 'Average segment win rate',
    d.avg_friendly_fraud_rate AS AVG(d.friendly_fraud_rate) COMMENT = 'Average friendly-fraud share of disputes',
    d.cfpb_complaints AS MAX(d.cfpb_complaint_count) COMMENT = 'CFPB complaints for the month (monthly benchmark; non-additive, do not SUM across reason codes)',
    d.cfpb_avg_monetary_relief AS AVG(d.cfpb_pct_monetary_relief) COMMENT = 'CFPB % closed with monetary relief',
    d.cfpb_avg_timely AS AVG(d.cfpb_pct_timely_response) COMMENT = 'CFPB % timely response',
    d.cfpb_avg_disputed AS AVG(d.cfpb_pct_consumer_disputed) COMMENT = 'CFPB % consumer-disputed outcome'
  )
  COMMENT = 'Dispute-intelligence semantic view (synthetic dispute book vs monthly complaint benchmark).';

-- 10. Output table, app stage, agent ---------------------------------------------
CREATE TABLE IF NOT EXISTS DISPUTE_REPORTS (
  run_id STRING DEFAULT UUID_STRING(), subject STRING, scope STRING, draft_md STRING, report_md STRING,
  status STRING, edits_applied INT, residual_hedges INT, edits STRING, fact_pack STRING, latency_ms INT,
  created_at TIMESTAMP_NTZ DEFAULT SYSDATE()
);

CREATE STAGE IF NOT EXISTS DISPUTE_APP_STAGE
  COMMENT = 'Streamlit app files (see sql/deploy_streamlit.sql)';

CREATE OR REPLACE AGENT DISPUTE_AGENT
  COMMENT = 'Chargeback & Dispute Intelligence agent (Cortex Analyst over DISPUTE_SV)'
  PROFILE = '{"display_name": "Dispute Intelligence Agent", "color": "green"}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto
  instructions:
    response: 'You are a payments dispute-ops analyst. Use ONLY figures from the Analyst tool. chargeback_rate is in basis points (100 bps = 1%). Overall win rate = total_won / total_resolved (do not average win_rate across segments for a portfolio figure). CFPB complaint counts are a MONTHLY benchmark: never sum them across reason codes or categories. Express USD in $M/$K. Never invent numbers. Do not name any real company, bank or card issuer. Be concise and cite the month.'
    orchestration: 'For any dispute, chargeback, reason-code, win-rate, friendly-fraud, or CFPB-complaint question use the DisputeIntelligence Analyst tool.'
    sample_questions:
      - question: 'How did chargeback volume in Nov-Dec compare to the prior 3 months, by reason category?'
      - question: 'What is our win rate by reason code, and where are we losing the most dollars?'
      - question: 'How do our dispute trends compare to CFPB complaint volume for the same period?'
  tools:
    - tool_spec:
        type: cortex_analyst_text_to_sql
        name: DisputeIntelligence
        description: 'Card disputes by merchant category, network, reason code and month, with a monthly consumer-complaint benchmark.'
  tool_resources:
    DisputeIntelligence:
      semantic_view: SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_SV
      execution_environment:
        type: warehouse
        warehouse: SNOWPACK_DISPUTE_INTEL_WH
  $$;

SELECT 'Setup complete: ' || (SELECT COUNT(*) FROM DISPUTE_FACT) || ' synthetic disputes' AS status;
