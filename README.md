# Chargeback & Dispute Intelligence

A Streamlit app that reads a card payments processor's dispute / chargeback book by reason code, network and merchant category, benchmarks it against real public consumer-complaint data, and calls Cortex `AI_COMPLETE` to draft a one-page note and then verify it — every number is pulled from governed data and the verifier pass flags unsupported or hedged claims. Setup also creates a Cortex Agent and a Cortex Analyst semantic view over the same data that you can explore in Snowsight.

Owner: Javier Soliz · Last reviewed: November 2026

## What it shows

- A **dispute book** broken out by reason-code category — Fraud (10.4 / 4837), Consumer Disputes (13.1 / 13.2 / 13.3 / 4853), Processing Errors (12.6) — with dispute count, disputed dollars, win rate and friendly-fraud rate, plus a monthly consumer-complaint benchmark.
- A **gallery** of generated chargeback notes, each badged Verified or Needs review.
- The app writes a grounded draft under strict DATA RULES and runs a Cortex `AI_COMPLETE` verifier pass that flags unsupported or hedged claims. Setup also creates a Cortex Analyst semantic view and a Cortex Agent over the same governed data — explorable in Snowsight for natural-language questions, not called by the app.

## How it works

- The **Streamlit app** builds a verified fact pack from the dispute benchmark, then calls Cortex **`AI_COMPLETE`** twice: once to draft a grounded chargeback note and once to fact-check it against the fact pack (Verified / Needs review).
- Setup also creates a **Cortex Agent** and a **Cortex Analyst semantic view** over the same data. These are explorable in Snowsight (AI & ML → Agents, and the semantic view) for natural-language questions — they are **not** called by the Streamlit app.
- The benchmark in the real-data variant is the **real, free CFPB consumer-complaint data** for payment-card products, joined to the internal dispute book **by month only** (there is no foreign key). Complaint counts are a market-wide, **non-additive** signal — never summed across reason codes.

## Prerequisites

- Snowflake Enterprise Edition or higher, in a region where Cortex AISQL and Cortex Agents are available.
- A Snowflake account with a role that can `CREATE DATABASE` and `CREATE WAREHOUSE`.
- Cortex AI functions available in your region (`AI_COMPLETE`; defaults to `claude-sonnet-4-5` — change the `MODEL` constant if your account differs).
- Streamlit in Snowflake enabled.
- Sample mode is fully synthetic and needs nothing external. The CFPB benchmark used by the real-data variant is free/public.

## Setup

1. Run [`app/setup_synthetic.sql`](app/setup_synthetic.sql). It creates the dedicated database, schema and warehouse, builds the synthetic dispute book **and** a synthetic complaint benchmark (no listing required), and creates the semantic view and agent.
2. Deploy [`app/streamlit_app.py`](app/streamlit_app.py) as a Streamlit in Snowflake app. Create its stage and the Streamlit app **inside `SNOWPACK_DISPUTE_INTEL.CORE`** so [`app/teardown.sql`](app/teardown.sql) removes them when it drops the database.
3. [`app/setup.sql`](app/setup.sql) documents the real-data variant: identical objects, but the complaint benchmark is the real CFPB consumer-complaint data (free Cybersyn CFPB complaint data; customer-facing Marketplace share `MARKETPLACE_CFPB_COMPLAINT`). Swap `DISPUTE_FACT` for your own chargeback ledger (same columns) to go live.

[`notebook/lab-dispute-intelligence.ipynb`](notebook/) walks through the whole pattern (semantic view → fact pack → grounded draft → verifier → persist) cell by cell.

## Customize with Cortex Code

Adapt this pack to your own disputes/chargebacks book with prompts like:

- "Add a new reason-code category for 'Authorization errors' (reason codes 11.1 / 11.2 / 11.3) to `DISPUTE_REASON_CODE` and reflect it in `DISPUTE_BENCHMARK` and the fact pack."
- "Change the grounded-draft DATA RULES in `streamlit_app.py` to also report chargeback-to-sales ratio per merchant category, and update the verifier to check it."
- "Repoint `DISPUTE_FACT` at my own chargeback ledger table and map my columns to the pack's schema so win rate and friendly-fraud rate still compute."

## Objects created

| Object | Type | Purpose |
|---|---|---|
| `SNOWPACK_DISPUTE_INTEL` | Database | Dedicated, isolated home for this pack |
| `SNOWPACK_DISPUTE_INTEL.CORE` | Schema | Holds all objects below |
| `SNOWPACK_DISPUTE_INTEL_WH` | Warehouse | XSMALL, auto-suspend 60s, used to build and run |
| `DISPUTE_CATEGORY` | Table | Merchant-category dim + chargeback-rate driver |
| `DISPUTE_REASON_CODE` | Table | Visa / Mastercard dispute reason-code dim |
| `DISPUTE_MERCHANT` | Table | Merchant dim (4 per category) |
| `DISPUTE_FACT` | Table | Synthetic per-dispute chargeback fact (holiday-skewed) |
| `DISPUTE_CFPB_BENCHMARK` | Table (sample) / View (real) | Monthly complaint benchmark — synthetic in sample mode, real CFPB in the real-data variant |
| `DISPUTE_BENCHMARK` | View | Wide benchmark: dispute book pre-aggregated to (category, network, reason, month) with rates + monthly complaint benchmark |
| `DISPUTE_DATA_SOURCE_INFO` | View | Data-mode marker read by the app/notebook |
| `DISPUTE_SV` | Semantic view | Cortex Analyst model over `DISPUTE_BENCHMARK` |
| `DISPUTE_REPORTS` | Table | Persisted generated notes + verifier verdicts |
| `DISPUTE_AGENT` | Cortex Agent | Natural-language agent over `DISPUTE_SV` |
| Streamlit app | Streamlit | Generates and galleries verified chargeback notes |

## Cost & time

Setup and a few note generations run in minutes on an XSMALL warehouse (auto-suspends after 60s). The main variable cost is Cortex `AI_COMPLETE` token usage — two calls (draft + verify) per generated note.

## Known limitations

- The dispute ledger (`DISPUTE_FACT`) is **synthetic** in both modes — a processor's own book has no public source.
- The CFPB benchmark is joined to internal disputes **by month only** (no FK), and complaint counts are **non-additive** — never summed across reason codes or categories.
- The hosted `try/` page uses mocked AI responses (illustrative, not live inference).
- Illustrative example, not a production system. Review and test before any production use. This is not an official Snowflake product.

## Cleanup

Run [`app/teardown.sql`](app/teardown.sql) to drop the database and warehouse created above.

## Learn more

- [Cortex AISQL (`AI_COMPLETE`)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql)
- [Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- [Streamlit in Snowflake](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)

## License

Apache 2.0 (see [`LICENSE`](LICENSE)). Illustrative example, as-is, not supported by Snowflake Support. Contains no customer data. Review and test before any production use.
