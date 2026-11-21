# Synthetic data

Everything in this pack is synthetic. The fictional processor is **Halvane Payments**; the 16
merchants (for example Quenfield Outfitters, Strevix Stream, Aerquill Air) are coined names. No
customer, cardholder or real company data is used.

## Generator

`sql/setup.sql` generates the data inside Snowflake, so there is nothing to download:

| Table | Rows | What it holds |
|---|---|---|
| `DISPUTE_CATEGORY` | 4 | Merchant categories with a base chargeback rate (bps) and base monthly volume |
| `DISPUTE_REASON_CODE` | 7 | Visa 10.4, 12.6, 13.1, 13.2, 13.3 and Mastercard 4837, 4853, with category, root cause and weight |
| `DISPUTE_MERCHANT` | 16 | Four merchants per category |
| `DISPUTE_FACT` | 9,960 | One row per dispute: merchant, reason code, network, filed date, amount, status, respond-by date |
| `DISPUTE_CFPB_BENCHMARK` | 24 | Monthly complaint benchmark (synthetic here; `sql/setup_cfpb.sql` swaps in real CFPB complaints) |

The window is 24 month-ends from July 2024 to the as-of date, **30 June 2026**.

**Seeded and deterministic.** Every random draw is `UNIFORM(lo, hi, HASH(<row key>, <salt>))`,
where the row key is (category, reason code, month, sequence). There is no `RANDOM()`, so
re-running setup produces identical rows. Checked on two consecutive runs (November 2026):

```sql
SELECT COUNT(*), HASH_AGG(*) FROM DISPUTE_FACT;           -- 9960, 4571422609776720502
SELECT COUNT(*), HASH_AGG(*) FROM DISPUTE_CFPB_BENCHMARK; -- 24,   3455697171749918135
```

The Sample mode files in `app/sample/` and `docs/try/data/` were captured from a Live run of
this generator (`scripts/capture_sample.py`), so Sample and Live show the same numbers.

## Planted stories

| # | Story | Where it shows | Value on this data set |
|---|---|---|---|
| 1 | **Holiday chargeback spike.** Disputes rise in Nov, Dec and Jan. | Overview trend (shaded band), KPI deltas, chargeback notes | 574 disputes a month in Nov–Jan vs 362 in other months (+59%) |
| 2 | **Fraud codes are the hardest to win.** Visa 10.4 and Mastercard 4837 (friendly fraud) win far less often than consumer-dispute codes. | Reason codes table and drawer, notes | 4837: 31.7%, 10.4: 35.3%, all other codes 53–56% |
| 3 | **10.4 is where the money goes.** The largest reason code also loses the most dollars. | "Dollars lost" bars, notes | $1.11M lost on 10.4, more than the next three codes combined |
| 4 | **Digital Goods runs the highest chargeback rate,** about 3–4x Grocery. | Merchants heatmap | Digital ~109 bps (138 in the holidays), Travel ~59, Retail ~38, Grocery ~27 |
| 5 | **One subscription merchant drives cancelled-recurring disputes** (added in v2). Strevix Stream carries most of Digital's Visa 13.2 disputes, a cancellation-flow problem worth fixing at the source. | Merchants table and drawer | Strevix Stream: 475 of 690 Digital 13.2 disputes (69%) |
| 6 | **Recent disputes are still in flight** (v2). Disputes filed in the last two months are mostly open or in pre-arbitration, with a respond-by date 30 days after filing. | Merchant drawer, status pills | 354 open, 390 pre-arbitration as of 30 June 2026 |

Win rate is always `won / (won + lost)`; open and pre-arbitration disputes are excluded. The
complaint benchmark is a monthly, market-wide signal: it is joined to the disputes **by month
only** and never summed across reason codes or categories.
