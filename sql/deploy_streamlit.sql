-- ============================================================================
-- Chargeback & Dispute Intelligence: deploy the Streamlit in Snowflake app
-- ----------------------------------------------------------------------------
-- Run after sql/setup.sql. First upload these files to the stage
-- SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_APP_STAGE, keeping the folders:
--   app/streamlit_app.py           -> streamlit_app.py
--   app/environment.yml            -> environment.yml
--   app/.streamlit/config.toml     -> .streamlit/config.toml
--   app/static/*                   -> static/   (logo.svg, Sora.woff2, OFL.txt)
--   app/sample/*.json (optional)   -> sample/   (adds the Sample switch in Snowsight)
-- Upload with Snowsight (Data > Databases > SNOWPACK_DISPUTE_INTEL > CORE >
-- Stages > DISPUTE_APP_STAGE > + Files), or from a terminal with PUT, e.g.
--   PUT file://app/streamlit_app.py @SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_APP_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- The app lives inside the pack database, so sql/cleanup.sql removes it.
-- ============================================================================
USE ROLE SNOWPACK_DISPUTE_INTEL_ROLE;
USE WAREHOUSE SNOWPACK_DISPUTE_INTEL_WH;
USE SCHEMA SNOWPACK_DISPUTE_INTEL.CORE;

CREATE OR REPLACE STREAMLIT DISPUTE_APP
  FROM '@SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_APP_STAGE'
  MAIN_FILE = 'streamlit_app.py'
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'   -- packages come from environment.yml
  QUERY_WAREHOUSE = SNOWPACK_DISPUTE_INTEL_WH
  TITLE = 'Rebuttra Dispute Desk'
  COMMENT = 'Chargeback & Dispute Intelligence example app';

SHOW STREAMLITS LIKE 'DISPUTE_APP';
