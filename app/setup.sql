-- ============================================================================
-- Chargeback & Dispute Intelligence — setup.sql  (real-data variant: real CFPB benchmark)
-- ----------------------------------------------------------------------------
-- A payments processor's (synthetic) card-dispute book is benchmarked against
-- REAL CFPB consumer complaints for payment-card products — free Cybersyn CFPB
-- complaint data already in the account (CFPB_COMPLAINT.DERIVED.CFPB_COMPLAINT_MAPPED;
-- the customer-facing equivalent is the free Marketplace share MARKETPLACE_CFPB_COMPLAINT).
--
-- A specific processor's dispute ledger has no public source, so DISPUTE_FACT is
-- synthetic in both modes; here the complaint BENCHMARK is REAL. Swap DISPUTE_FACT
-- for your own chargeback data (same columns) to go live.
--
-- Prereq: the free CFPB complaint data (or MARKETPLACE_CFPB_COMPLAINT share).
-- Run setup_synthetic.sql instead for a no-listing sample run.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS SNOWPACK_DISPUTE_INTEL;
CREATE SCHEMA IF NOT EXISTS SNOWPACK_DISPUTE_INTEL.CORE
  COMMENT = 'Chargeback & Dispute Intelligence: card dispute / chargeback benchmarking';
CREATE WAREHOUSE IF NOT EXISTS SNOWPACK_DISPUTE_INTEL_WH WITH WAREHOUSE_SIZE='XSMALL' AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE;
USE WAREHOUSE SNOWPACK_DISPUTE_INTEL_WH;
USE SCHEMA SNOWPACK_DISPUTE_INTEL.CORE;

-- Type-switch safety: DISPUTE_CFPB_BENCHMARK is a VIEW here, a TABLE in setup_synthetic.sql.
DROP TABLE IF EXISTS DISPUTE_CFPB_BENCHMARK;
DROP VIEW  IF EXISTS DISPUTE_CFPB_BENCHMARK;

-- 1. Merchant-category dim + chargeback-rate driver -------------------------
CREATE OR REPLACE TABLE DISPUTE_CATEGORY (
  merchant_category STRING, category_name STRING, base_cb_bps FLOAT, base_txn INT
);
INSERT INTO DISPUTE_CATEGORY VALUES
  ('RETAIL','Retail & E-commerce',   42,  900000),
  ('TRAVEL','Travel & Hospitality',  65,  300000),
  ('DIGITAL','Digital Goods & Subscriptions', 120, 600000),
  ('GROCERY','Grocery & Essentials', 30,  500000);

-- 2. Dispute reason-code dim (Visa dotted + Mastercard 4-digit) --------------
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

-- 3. Merchant dim (4 merchants per category, stable merchant_seq) ------------
CREATE OR REPLACE TABLE DISPUTE_MERCHANT (
  merchant_id INT, merchant_name STRING, mcc STRING, merchant_category STRING, merchant_seq INT
);
INSERT INTO DISPUTE_MERCHANT VALUES
  (101,'Northwind Retail','5651','RETAIL',1),(102,'Harbor Goods','5732','RETAIL',2),(103,'Union Marketplace','5311','RETAIL',3),(104,'Beacon Outfitters','5651','RETAIL',4),
  (201,'Skyline Travel','4722','TRAVEL',1),(202,'Coastline Resorts','7011','TRAVEL',2),(203,'Summit Air','3000','TRAVEL',3),(204,'Wayfarer Tours','4722','TRAVEL',4),
  (301,'Streamly','5815','DIGITAL',1),(302,'PlayVault','5816','DIGITAL',2),(303,'CloudDesk SaaS','5817','DIGITAL',3),(304,'NovaGames','5816','DIGITAL',4),
  (401,'FreshCart','5411','GROCERY',1),(402,'GreenBasket','5411','GROCERY',2),(403,'DailyPantry','5499','GROCERY',3),(404,'MarketLane','5411','GROCERY',4);

-- 24 month-ends ending 2026-06-30, holiday spike factor for Nov/Dec/Jan ------
CREATE OR REPLACE TEMP TABLE DISPUTE_months AS
SELECT LAST_DAY(DATEADD(month, SEQ4(), '2024-07-01')) AS month_end, SEQ4() AS m_idx,
       (CASE WHEN MONTH(LAST_DAY(DATEADD(month, SEQ4(), '2024-07-01'))) IN (11,12,1) THEN 1.6 ELSE 1.0 END) AS holiday_f
FROM TABLE(GENERATOR(ROWCOUNT => 24));

-- 4. Synthetic per-dispute fact (swap for your own chargeback ledger) --------
CREATE OR REPLACE TEMP TABLE DISPUTE_cells AS
SELECT c.merchant_category, r.reason_code, r.network, r.is_friendly_fraud, m.month_end, m.holiday_f,
       LEAST(600, GREATEST(2, ROUND(c.base_txn*(c.base_cb_bps/10000.0)*r.weight*m.holiday_f/40.0))) AS target_count
FROM DISPUTE_CATEGORY c CROSS JOIN DISPUTE_REASON_CODE r CROSS JOIN DISPUTE_months m;

CREATE OR REPLACE TEMP TABLE DISPUTE_nums AS
SELECT SEQ4() AS n FROM TABLE(GENERATOR(ROWCOUNT => 600));

CREATE OR REPLACE TABLE DISPUTE_FACT
  COMMENT = 'SYNTHETIC per-dispute chargeback fact. Replace with your own chargeback ledger (same columns) to go live.'
AS
SELECT ROW_NUMBER() OVER (ORDER BY cl.month_end, cl.merchant_category, cl.network, cl.reason_code, nm.n) AS dispute_id,
       2000000000 + (ROW_NUMBER() OVER (ORDER BY cl.month_end, cl.merchant_category, cl.network, cl.reason_code, nm.n)) AS transaction_id,
       mm.merchant_id, mm.merchant_name, cl.merchant_category, cl.reason_code, cl.network,
       DATEADD(day, UNIFORM(0, 27, RANDOM(101)), DATE_TRUNC('month', cl.month_end))::date AS date_filed,
       cl.month_end,
       ROUND(UNIFORM(2500, 120000, RANDOM(202))/100.0, 2) AS dispute_amount,
       ROUND(ROUND(UNIFORM(2500, 120000, RANDOM(202))/100.0, 2) * (1 + UNIFORM(0, 60, RANDOM(203))/100.0), 2) AS transaction_amount,
       cl.is_friendly_fraud,
       CASE WHEN UNIFORM(0,100,RANDOM(204)) < 12 THEN 'open'
            WHEN UNIFORM(0,100,RANDOM(205)) < 8  THEN 'pre-arb'
            WHEN UNIFORM(0,100,RANDOM(206)) < (CASE WHEN cl.is_friendly_fraud THEN 35 ELSE 55 END) THEN 'won'
            ELSE 'lost' END AS status
FROM DISPUTE_cells cl
JOIN DISPUTE_nums nm ON nm.n < cl.target_count
JOIN DISPUTE_MERCHANT mm ON mm.merchant_category = cl.merchant_category AND mm.merchant_seq = MOD(nm.n,4)+1;

-- 5. Complaint benchmark — REAL CFPB payment-card complaints (monthly) -------
--    CFPB_COMPLAINT_MAPPED is a complaint fact (one row per complaint), so no
--    PIT vintage dedup is needed here. Window matches the dispute book.
CREATE OR REPLACE VIEW DISPUTE_CFPB_BENCHMARK
  COMMENT = 'REAL CFPB consumer complaints for payment-card products, aggregated monthly (free Cybersyn CFPB complaint data).'
AS
SELECT LAST_DAY(DATE_RECEIVED) AS month_end,
       COUNT(*) AS cfpb_complaint_count,
       ROUND(AVG(IFF(COMPANY_RESPONSE_TO_CONSUMER='Closed with monetary relief',1,0))*100, 1) AS cfpb_pct_monetary_relief,
       ROUND(AVG(IFF(TIMELY_RESPONSE,1,0))*100, 1) AS cfpb_pct_timely_response,
       ROUND(AVG(IFF(CONSUMER_DISPUTED='Yes',1,0))*100, 1) AS cfpb_pct_consumer_disputed
FROM CFPB_COMPLAINT.DERIVED.CFPB_COMPLAINT_MAPPED
WHERE PRODUCT IN ('Credit card','Credit card or prepaid card','Money transfer, virtual currency, or money service','Prepaid card')
  AND DATE_RECEIVED BETWEEN '2024-07-01' AND '2026-06-30'
GROUP BY 1;

-- 6. Wide benchmark view (identical to synthetic) ----------------------------
CREATE OR REPLACE VIEW DISPUTE_BENCHMARK
  COMMENT = 'Dispute book pre-aggregated to (merchant_category, network, reason_code, month) with chargeback/win/friendly-fraud rates and a REAL monthly CFPB complaint benchmark (non-additive).'
AS
WITH f AS (
  SELECT merchant_category, network, reason_code, month_end,
         COUNT(*) AS dispute_count,
         SUM(dispute_amount) AS total_dispute_amount,
         SUM(transaction_amount) AS total_transaction_amount,
         SUM(IFF(status='won',1,0)) AS won_count,
         SUM(IFF(status IN ('won','lost'),1,0)) AS resolved_count,
         SUM(IFF(is_friendly_fraud,1,0)) AS friendly_fraud_count
  FROM DISPUTE_FACT GROUP BY 1,2,3,4
),
cm AS (
  SELECT f.merchant_category, f.month_end,
         ROUND(SUM(f.dispute_count) / NULLIF(MAX(c.base_cb_bps)/10000.0,0)) AS processed_txn_count
  FROM f JOIN DISPUTE_CATEGORY c USING (merchant_category)
  GROUP BY 1,2
)
SELECT f.merchant_category, cat.category_name, f.network, f.reason_code,
       rc.reason_category, rc.reason_name, rc.is_friendly_fraud,
       f.month_end, YEAR(f.month_end) AS report_year, QUARTER(f.month_end) AS report_quarter,
       f.dispute_count, f.total_dispute_amount, f.total_transaction_amount,
       f.won_count, f.resolved_count, f.friendly_fraud_count,
       cm.processed_txn_count,
       ROUND(f.dispute_count / NULLIF(cm.processed_txn_count,0) * 10000, 2) AS chargeback_rate_bps,
       ROUND(f.won_count / NULLIF(f.resolved_count,0), 3) AS win_rate,
       ROUND(f.friendly_fraud_count / NULLIF(f.dispute_count,0), 3) AS friendly_fraud_rate,
       b.cfpb_complaint_count, b.cfpb_pct_monetary_relief, b.cfpb_pct_timely_response, b.cfpb_pct_consumer_disputed
FROM f
JOIN DISPUTE_REASON_CODE rc ON rc.reason_code = f.reason_code AND rc.network = f.network
JOIN DISPUTE_CATEGORY cat ON cat.merchant_category = f.merchant_category
JOIN cm ON cm.merchant_category = f.merchant_category AND cm.month_end = f.month_end
LEFT JOIN DISPUTE_CFPB_BENCHMARK b ON b.month_end = f.month_end;

-- 7. Data-source marker -------------------------------------------------------
CREATE OR REPLACE VIEW DISPUTE_DATA_SOURCE_INFO AS
SELECT 'marketplace' AS mode,
       'Synthetic dispute book benchmarked against REAL CFPB consumer complaints for payment-card products (free Cybersyn CFPB complaint data; Marketplace share MARKETPLACE_CFPB_COMPLAINT). Swap DISPUTE_FACT for your own chargeback ledger to go live.' AS note;

-- 8. Semantic view (identical to synthetic) ----------------------------------
CREATE OR REPLACE SEMANTIC VIEW DISPUTE_SV
  TABLES ( d AS SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_BENCHMARK PRIMARY KEY (merchant_category, network, reason_code, month_end)
           WITH SYNONYMS = ('disputes','chargebacks','dispute benchmark')
           COMMENT = 'Card disputes by merchant category, network, reason code and month, with a monthly CFPB consumer-complaint benchmark' )
  FACTS (
    d.dispute_count AS DISPUTE_COUNT,
    d.total_dispute_amount AS TOTAL_DISPUTE_AMOUNT,
    d.total_transaction_amount AS TOTAL_TRANSACTION_AMOUNT,
    d.won_count AS WON_COUNT,
    d.resolved_count AS RESOLVED_COUNT,
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
    d.total_friendly_fraud AS SUM(d.friendly_fraud_count) COMMENT = 'Friendly-fraud disputes',
    d.avg_chargeback_rate_bps AS AVG(d.chargeback_rate_bps) COMMENT = 'Average chargeback rate (bps of processed txns)',
    d.avg_win_rate AS AVG(d.win_rate) COMMENT = 'Average segment win rate',
    d.avg_friendly_fraud_rate AS AVG(d.friendly_fraud_rate) COMMENT = 'Average friendly-fraud share of disputes',
    d.cfpb_complaints AS MAX(d.cfpb_complaint_count) COMMENT = 'CFPB complaints for the month (monthly benchmark; non-additive, do not SUM across reason codes)',
    d.cfpb_avg_monetary_relief AS AVG(d.cfpb_pct_monetary_relief) COMMENT = 'CFPB % closed with monetary relief',
    d.cfpb_avg_timely AS AVG(d.cfpb_pct_timely_response) COMMENT = 'CFPB % timely response',
    d.cfpb_avg_disputed AS AVG(d.cfpb_pct_consumer_disputed) COMMENT = 'CFPB % consumer-disputed outcome'
  )
  COMMENT = 'Dispute-intelligence semantic view (synthetic dispute book vs REAL CFPB complaint benchmark).';

-- 9. Output table + agent (identical to synthetic) ---------------------------
CREATE TABLE IF NOT EXISTS DISPUTE_REPORTS (
  run_id STRING DEFAULT UUID_STRING(), subject STRING, draft_md STRING, report_md STRING,
  status STRING, edits_applied INT, residual_hedges INT, created_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE AGENT DISPUTE_AGENT
  COMMENT = 'Chargeback & Dispute Intelligence agent (Cortex Analyst over DISPUTE_SV)'
  PROFILE = '{"display_name": "Dispute Intelligence Agent", "color": "blue"}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto
  instructions:
    response: 'You are a payments dispute-ops analyst. Use ONLY figures from the Analyst tool. chargeback_rate is in basis points (100 bps = 1%). Overall win rate = total_won / total_resolved (do not average win_rate across segments for a portfolio figure). CFPB complaint counts are a MONTHLY benchmark: never sum them across reason codes or categories. Express USD in $M/$K. Never invent numbers. Be concise and cite the month.'
    orchestration: 'For any dispute, chargeback, reason-code, win-rate, friendly-fraud, or CFPB-complaint question use the DisputeIntelligence Analyst tool.'
    sample_questions:
      - question: 'How did chargeback volume in Nov-Dec compare to the prior 3 months, by reason category?'
      - question: 'What is our win rate by reason code, and where are we losing the most dollars?'
      - question: 'How do our dispute trends compare to CFPB complaint volume for the same period?'
  tools:
    - tool_spec:
        type: cortex_analyst_text_to_sql
        name: DisputeIntelligence
        description: 'Card disputes by merchant category, network, reason code and month, with a REAL monthly CFPB complaint benchmark.'
  tool_resources:
    DisputeIntelligence:
      semantic_view: SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_SV
  $$;
