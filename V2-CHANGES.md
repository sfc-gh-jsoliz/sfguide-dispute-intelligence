# What changed in v2

This branch rebuilds Chargeback & Dispute Intelligence to the Snow Packs v2 bar (see
`COCO-V2-INSTRUCTIONS.md`). Your data stories, Snowflake features, Streamlit stack and owner
line are unchanged. The app, the landing page and the polish are new.

## Screen by screen

| Screen | v1 | v2 | Why |
|---|---|---|---|
| App shell | Streamlit title, a sidebar button, a warning banner for the data mode | Branded **Rebuttra Dispute Desk** shell: teal masthead with logo and top navigation (5 screens), user/role chip, **Sample/Live** environment badge and switch, as-of date | v2 asks for a branded, enterprise-looking shell with a visible mode badge |
| Overview | Not present (the app opened on the note gallery) | KPI tiles with trends (disputes, disputed $, win rate, dollars lost, chargeback bps), a stacked monthly chart by reason category with holiday bands and the complaint benchmark on its own axis, a "What stands out" panel, and dollars-lost bars by reason code. All from a `SEMANTIC_VIEW()` query | Shows the holiday-spike and fraud-win-rate stories at a glance, and makes the semantic view a runtime feature instead of setup-only |
| Reason codes | Not present | Sortable, filterable table (network, category, search) with win-rate bars and status; selecting a row opens a detail panel with trend, merchant-category split and root cause | Rich tables and drill-downs |
| Merchants | Not present | Chargeback-rate heatmap (category × month) and a merchant table with a concentration flag; a merchant panel shows disputes in flight with respond-by dates and status pills | New planted story (one subscription merchant drives Visa 13.2) and in-flight disputes |
| Chargeback notes | One button, spinner, gallery of cards | Two scopes (holiday spike, or first vs latest month). Staged progress steps, streaming reveal, `[F#]` citation chips tied to the fact-pack rows, an animated Verified / Needs review stamp, a **Try to break it** button that inserts a hedge and re-runs only the verifier, and a docket-style gallery that opens saved notes in a panel | v2 AI bar: staged steps, streaming, citations, and a visible quality gate |
| Ask the desk | Agent only in Snowsight | In-app chat with the Cortex Agent: three sample questions, staged steps, streamed answer, result table, and the generated SQL as the source | Cortex Agents / Analyst were claimed but not used by the app; now they run in Live mode |
| Hosted example (`/try/`) | Static page with mocked notes | Static copy of all five screens on data captured from a Live run, labeled "Sample AI response", 4–8 s simulated delays, sortable tables, drawers, tooltips; works at 390 px | v2 hosted-example bar |
| Landing page | Shared template look | Own identity: teal hero with a CSS stack of chargeback tickets and a Verified stamp, problem-first headline, captioned screenshots with matching alt text, capability table with measured timings, dark mode, self-hosted Sora font, no CDN scripts | v2 landing-page bar |

## Data and SQL

- SQL moved to `sql/`: `setup.sql` is the synthetic default (was `app/setup_synthetic.sql`), `setup_cfpb.sql` swaps in the real CFPB benchmark on top of it (was `app/setup.sql`), `cleanup.sql` replaces `app/teardown.sql`, and `deploy_streamlit.sql` is new.
- **Least-privilege role** `SNOWPACK_DISPUTE_INTEL_ROLE` owns everything; cleanup drops it too.
- **Deterministic generator:** `RANDOM(seed)` is not guaranteed to assign the same values to the same rows across runs. Every draw is now `UNIFORM(lo, hi, HASH(row key, salt))`; two runs give identical `HASH_AGG` (see `data/README.md`).
- **Re-run bug fixed:** `DROP VIEW IF EXISTS` failed when the object was a table, so a second run of either setup script errored. Both scripts now try both drops quietly.
- **Chargeback rate is no longer constant:** processed volume was back-computed from disputes, so each category's rate was flat. Volume is now modeled per category and month (+25% in the holidays, +1% a month), so the rate moves (Digital ~109 bps, 138 in the holidays).
- **Status depends on age:** open and pre-arbitration disputes are now only the recent ones (March–June 2026), each with a respond-by date.
- **Merchant names:** some v1 names matched real companies. All 16 merchants now have coined names.
- **New planted story:** Strevix Stream carries 69% of Digital's Visa 13.2 (cancelled recurring) disputes.
- The semantic view gains `LOST_AMOUNT`, `total_lost_usd` and a non-additive `processed_txn` metric. The agent spec pins its warehouse and is told not to name real companies.
- `DISPUTE_REPORTS` gains `scope`, `edits`, `fact_pack` and `latency_ms` (the notebook's inserts still work).
- AI fixes: `AI_COMPLETE` returns a JSON-encoded string, which broke the verifier's parsing in v1 (every note came back "Needs review / unparseable"). The output is now decoded, the verifier's last JSON object is taken (it sometimes re-checks itself), and both prompts share the same rules on rounding and percentage changes.

## What to do after merging

1. **GitHub Pages:** Settings > Pages > Deploy from a branch > `main` / `/docs`. The guide moves to `docs/index.html` and the hosted example to `docs/try/`. `docs/.nojekyll` is included. Until you switch, the root `index.html` and `try/index.html` redirect to `docs/`, so existing links keep working either way.
2. **Check the site** once Pages shows "built": open `/` and `/try/` signed out, on a phone and on desktop.
3. **No build step.** The app is plain Streamlit and the hosted example is static HTML/JS/CSS.
4. **To refresh the Sample data** after changing the data or prompts: run `sql/setup.sql`, then `python scripts/capture_sample.py` with the key-pair environment variables from the README. It rewrites `app/sample/` and `docs/try/data/`.
5. **To redeploy the Streamlit in Snowflake app:** upload the `app/` files to `DISPUTE_APP_STAGE` and run `sql/deploy_streamlit.sql` (steps in the README).
6. The catalog card images are in `docs/catalog/` (960×600, under 100 KB). The Snow Packs maintainers will update the catalog entry's screenshots in a separate PR.

`COCO-V2-INSTRUCTIONS.md` is the checklist used for this rebuild; give it to your CoCo to bring your other packs to v2.
