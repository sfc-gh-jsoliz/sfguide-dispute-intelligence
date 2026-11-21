# Chargeback & Dispute Intelligence

Explain a chargeback spike in one page where every number backs up. A Streamlit app, branded as the fictional **Rebuttra Dispute Desk**, reads a card processor's dispute book by reason code, network and merchant. It benchmarks the book against a monthly consumer-complaint signal and calls Cortex `AI_COMPLETE` twice: once to draft a cited chargeback note from a small fact pack, and once to fact-check it, stamping the note **Verified** or **Needs review**. A Cortex Agent answers plain-English questions with Cortex Analyst over the same semantic view.

- **Guide:** https://sfc-gh-jsoliz.github.io/sfguide-dispute-intelligence/
- **Try it, no account:** https://sfc-gh-jsoliz.github.io/sfguide-dispute-intelligence/try/

Owner: Javier Soliz · Last reviewed: November 2026

> Synthetic data and illustrative logic only. Halvane Payments, Rebuttra and every merchant are fictional. Not production software, and not regulatory, compliance or legal advice.

## What it shows

| Screen | What you see | Snowflake capability |
|---|---|---|
| Overview | Disputes, dollars, win rate, dollars lost and chargeback rate (bps) for 24 months; stacked monthly trend by reason category with holiday bands and the complaint benchmark | Semantic View `DISPUTE_SV`, queried with `SEMANTIC_VIEW()` |
| Reason codes | Every Visa and Mastercard code, sortable and filterable; a detail panel per code with its trend, merchant-category split and root cause | Semantic View `DISPUTE_SV` |
| Merchants | Chargeback-rate heatmap (category × month); merchant table with a concentration flag; a panel per merchant with disputes in flight and respond-by dates | Semantic View + Snowflake SQL on `DISPUTE_FACT` |
| Chargeback notes | A note drafted from a fact pack with citations (F1–F6), a verifier stamp, a "Try to break it" re-check, and a gallery of saved notes | Cortex `AI_COMPLETE` (draft + verifier), notes stored in `DISPUTE_REPORTS` |
| Ask the desk | Plain-English answers with the result table and the generated SQL | Cortex Agent `DISPUTE_AGENT` with Cortex Analyst over `DISPUTE_SV` |

The planted data stories (holiday spike, fraud codes hardest to win, one subscription merchant driving cancelled-recurring disputes) are documented in [`data/README.md`](data/README.md).

## Prerequisites

- A Snowflake account (Standard Edition is enough) in a region with Cortex AI (`AI_COMPLETE` with `claude-sonnet-4-5`, Cortex Agents, Cortex Analyst), or with cross-region inference enabled. Change the `MODEL` constant in `app/streamlit_app.py` if your account uses another model.
- `ACCOUNTADMIN` (or `USERADMIN` + `SECURITYADMIN`) and `SYSADMIN` to run setup. Setup creates a least-privilege role, `SNOWPACK_DISPUTE_INTEL_ROLE`, that owns only the pack's objects; everything after the first block runs as that role.
- Streamlit in Snowflake for the hosted app, or Python 3.11+ to run it locally.
- Tested November 2026 with Streamlit 1.52.2, Altair 5.5.0, pandas 2.2.3 and snowflake-snowpark-python 1.42 (local) on AWS us-east-1.

## Quick start: no account (Sample mode)

```bash
git clone https://github.com/sfc-gh-jsoliz/sfguide-dispute-intelligence
cd sfguide-dispute-intelligence/app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

With no Snowflake settings the app opens in **Sample** mode on `app/sample/*.json`, captured from a Live run. AI answers are labeled **Sample AI response** and replay after a simulated 4–8 s delay with the same staged steps the live path runs. The hosted [`/try/`](https://sfc-gh-jsoliz.github.io/sfguide-dispute-intelligence/try/) page is a static copy of the same screens on the same data.

## Run it live

1. **Setup.** Run [`sql/setup.sql`](sql/setup.sql) top to bottom in a Snowsight worksheet. It creates the role, warehouse and database, generates the synthetic book, and creates the semantic view, the reports table, the app stage and the agent. It took 16–18 s in testing.
2. **Optional: real complaint benchmark.** If your account has the free CFPB consumer-complaint data mounted as `CFPB_COMPLAINT`, run [`sql/setup_cfpb.sql`](sql/setup_cfpb.sql) to swap the synthetic benchmark for real monthly payment-card complaints. The dispute book stays synthetic.
3. **Deploy the app to Streamlit in Snowflake.** Upload `app/streamlit_app.py`, `app/environment.yml`, `app/.streamlit/config.toml`, `app/static/*` and (optionally) `app/sample/*.json` to the stage `SNOWPACK_DISPUTE_INTEL.CORE.DISPUTE_APP_STAGE`, keeping the folders, then run [`sql/deploy_streamlit.sql`](sql/deploy_streamlit.sql). The app uses the warehouse runtime, and its packages come from `environment.yml`. Open it from **Projects > Streamlit > Rebuttra Dispute Desk**. It opens in Live mode; if you uploaded the sample files, the Sample switch also works there.
4. **Or run locally in Live mode** with key-pair auth (never a password in the browser). Register a public key on your user ([key-pair authentication](https://docs.snowflake.com/en/user-guide/key-pair-auth)), then:

   ```bash
   export SNOWFLAKE_ACCOUNT=<your_account_identifier>
   export SNOWFLAKE_USER=<YOUR_USER>
   export SNOWFLAKE_PRIVATE_KEY_PATH=~/.snowflake/keys/<your_key>.p8
   # optional: SNOWFLAKE_ROLE (default SNOWPACK_DISPUTE_INTEL_ROLE), SNOWFLAKE_WAREHOUSE
   streamlit run app/streamlit_app.py
   ```

   The header badge shows **Live**. If you pick Live without these settings, the app shows the steps instead of switching. If a Live call fails, it shows the error and never falls back to sample data.
5. **Refresh the Sample bundle** after changing data or prompts: `python scripts/capture_sample.py` (same environment variables). It writes `app/sample/` and copies it to `docs/try/data/`.

### What gets created

| Object | Type | Purpose |
|---|---|---|
| `SNOWPACK_DISPUTE_INTEL_ROLE` | Role | Least-privilege role: `CORTEX_USER`, warehouse usage, and create rights in the pack schema only |
| `SNOWPACK_DISPUTE_INTEL_WH` | Warehouse | XSMALL, `AUTO_SUSPEND = 60` |
| `SNOWPACK_DISPUTE_INTEL` / `CORE` | Database / schema | Holds everything below |
| `DISPUTE_CATEGORY`, `DISPUTE_REASON_CODE`, `DISPUTE_MERCHANT` | Tables | Dimensions: 4 categories, 7 reason codes, 16 fictional merchants |
| `DISPUTE_FACT` | Table | 9,960 synthetic disputes, hash-seeded and deterministic |
| `DISPUTE_CFPB_BENCHMARK` | Table (or view after `setup_cfpb.sql`) | Monthly complaint benchmark |
| `DISPUTE_BENCHMARK` | View | Book aggregated to category × network × reason × month, with rates |
| `DISPUTE_DATA_SOURCE_INFO` | View | Synthetic or real-benchmark marker |
| `DISPUTE_SV` | Semantic view | Business definitions for Cortex Analyst and the app |
| `DISPUTE_REPORTS` | Table | Saved notes, verdicts, fact packs and latency |
| `DISPUTE_APP_STAGE` | Stage | App files |
| `DISPUTE_AGENT` | Cortex Agent | Cortex Analyst over `DISPUTE_SV` |
| `DISPUTE_APP` | Streamlit | Created by `sql/deploy_streamlit.sql` |

## Cost and time

Measured on the test account in November 2026:

| Step | Time | Cost |
|---|---|---|
| `sql/setup.sql` | 16–18 s | About 0.02 credits (XSMALL, including the 60 s auto-suspend) |
| Overview / Reason codes / Merchants in Live mode | Under 1 s per query once the warehouse is warm | Warehouse time only |
| One chargeback note (draft + verify) | 8–11 s | Two `AI_COMPLETE` calls, about 0.009 AI credits |
| "Try to break it" re-verify | 3–6 s | One `AI_COMPLETE` call |
| One "Ask the desk" answer | 25–34 s | Cortex Agent usage (billed separately; not broken out in the usage views we checked) |

The whole build and test session (eight setup runs, three sample captures and the UI tests) used about 0.62 warehouse credits and 0.22 AI credits for 51 `AI_COMPLETE` calls. Your numbers depend on region, model and warehouse.

## Known limitations

- The dispute ledger (`DISPUTE_FACT`) is synthetic in both variants; a processor's own book has no public source. Processed-transaction volume is modeled per category and month.
- The complaint benchmark is joined to disputes **by month only** (no foreign key), and complaint counts are non-additive: they are never summed across reason codes or categories.
- `sql/setup_cfpb.sql` was not run in the test account (no CFPB data mounted there); the synthetic variant was verified live end to end.
- The verifier is an AI pass, not a guarantee. It caught every planted hedge in testing, but it can be strict about rounding or miss a subtle error. Treat "Verified" as a check, not an audit.
- The agent's answers are not run through the verifier.
- Streamlit opens detail panels as dialogs; deep links point to a screen, not to a single reason code or merchant.
- In Streamlit in Snowflake the Sora font loads only if your runtime serves `app/static/`; otherwise the app uses the system font.

## Customize with Cortex Code

- "Explain this pack's data model and map my chargeback ledger to `DISPUTE_FACT` without changing any objects."
- "Add Visa 11.x authorization reason codes to `DISPUTE_REASON_CODE` and carry them through `DISPUTE_BENCHMARK`, `DISPUTE_SV` and the app."
- "Change the note's DATA RULES to also report chargeback-to-sales ratio per merchant category, and make the verifier check it."

[`notebook/lab-dispute-intelligence.ipynb`](notebook/) walks through the same pattern cell by cell: semantic view → fact pack → grounded draft → verifier → persist.

## Cleanup

Run [`sql/cleanup.sql`](sql/cleanup.sql). It drops the database (tables, views, semantic view, agent, stage and Streamlit app), the warehouse and the role, and is safe to re-run.

## Repository layout

```text
app/streamlit_app.py     The app (one file; paste-able into Snowsight)
app/sample/              Sample-mode data captured from a Live run
app/static/, .streamlit/ Logo, font, theme
sql/                     setup.sql, setup_cfpb.sql, deploy_streamlit.sql, cleanup.sql
data/README.md           Generator and planted stories
docs/                    GitHub Pages guide, hosted example (docs/try/), DESIGN.md, screenshots
scripts/                 capture_sample.py, check_contrast.py
notebook/                Step-by-step lab
```

## Learn more

- [Semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/overview)
- [AI_COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/ai_complete)
- [Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- [Streamlit in Snowflake](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)

## License

Apache 2.0 (see [`LICENSE`](LICENSE)). The Sora font in `docs/fonts/` and `app/static/` is under the SIL Open Font License (`OFL.txt`). This is an illustrative example provided as-is: it is not an official Snowflake product and is not supported by Snowflake Support. It contains no customer data. Review and test before any production use.
