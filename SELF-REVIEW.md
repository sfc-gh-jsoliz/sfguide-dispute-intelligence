# Self-review (v2 rebuild, November 2026)

Every item from the build standard's "Before you call it done" list, the v2 bar, and every
CONTRIBUTING Must and Should, checked on the `v2-rebuild` branch. All results are from this
session. Live checks ran in a Snowflake test account with key-pair auth; Pages checks ran on the
fork's Pages site (`sfc-gh-ooral.github.io/sfguide-dispute-intelligence`, serving this branch
from `/docs`), because the original repo's Pages will only show v2 after the merge.

## Before you call it done

| Item | Result | Evidence |
|---|---|---|
| App runs from a fresh clone in Sample (mock) mode | Pass | Fresh `git clone` + `pip install -r requirements.txt` + `streamlit run`: all 5 screens at 1440 and 390 px, no exceptions |
| Setup → Live mode → cleanup in a clean role | Pass | `sql/setup.sql` (16–18 s, run 8 times), every screen and AI action in Live mode as `SNOWPACK_DISPUTE_INTEL_ROLE`, `sql/cleanup.sql`; `SHOW DATABASES/WAREHOUSES/ROLES/AGENTS/STREAMLITS/SEMANTIC VIEWS` all returned 0 rows; cleanup re-run is a no-op |
| Grep files and git history for secrets, account identifiers, real user names | Pass at HEAD; **one finding in history** | No keys, tokens, account identifiers or hostnames anywhere. A committed `app/__pycache__/*.pyc` (removed at HEAD in `c52e585`) embeds a local file path with a user name in three earlier branch commits. Not rewritten (history rewrites need maintainer approval); a squash merge keeps it out of `main` |
| Pages URL and `/try/` signed out; phone width and dark mode | Pass | Guide and `/try/` return 200; every JS/CSS referenced from `/try/index.html` returns 200; `.nojekyll` 200; Playwright at 390 px and 1440 px, light and dark: no horizontal scroll, no console errors, all flows (drawers, note, re-verify, agent answer) complete |
| Story beats visible in a screenshot | Pass | Holiday spike (overview), fraud codes hardest to win and 10.4 most dollars lost (overview, reason-code panel), Digital highest rate (merchants heatmap), Strevix 13.2 concentration (merchant panel), verifier catches a hedge (note-needs-review) |

## v2 bar

| Item | Result | Notes |
|---|---|---|
| `docs/DESIGN.md` first: brand, logo SVG, voice, palette, type, layout, density, charts, motion, distinctness vs 5+ packs | Pass | Rebuttra Dispute Desk; compared against 10 live packs |
| Branded shell: navigation, logo, user/role chip, Sample/Live badge | Pass | Top-nav masthead; chip "Dispute analyst · Halvane Payments"; env badge + switch |
| KPI tiles with trends, real charts with tooltips and legends | Pass | Altair (app) and SVG (hosted) with hover tooltips and legends |
| Tables with sort, filter, status pills | Pass | Sortable/filterable grids; pills in panels and the hosted tables |
| Detail drawers or panels | Pass | Reason-code and merchant panels; saved-note panel |
| Empty, loading and error states | Pass | Empty filter results and empty gallery; skeleton shimmer while Live queries run; Live errors shown with guidance, never a silent fallback |
| Motion with taste | Pass | Card fade-up, odometer counters, stamp press, streaming caret, ticket deal-in on the landing page; `prefers-reduced-motion` respected |
| Design tokens from DESIGN.md; WCAG AA | Pass | Tokens in `config.toml` + CSS; `scripts/check_contrast.py` passes every text pair |
| Dark mode | Pass (landing page); Skipped (app) | Landing page has a dark scheme. The Streamlit app is light by design (DESIGN.md); Streamlit's own dark theme is available from its menu but was not styled or tested |
| AI: 4–8 s delay with staged steps, streaming reveal, citations, "Sample AI response" label | Pass | Sample mode waits 4–8 s across truthful steps; Live mode shows the same steps and the measured latency; notes cite fact-pack rows F1–F6; agent answers show their SQL |
| Seeded deterministic generator + `data/README.md` | Pass | HASH-seeded; two runs gave identical `HASH_AGG` |
| Only claim what runs in Live mode; Preview labels | Pass | Semantic View, AI_COMPLETE, Cortex Agents/Analyst and Streamlit in Snowflake all run from the app in Live mode; all four are GA per the docs (no Preview labels needed) |
| Key-pair auth only | Pass | All SQL and the app's Live mode used key-pair auth |
| App screenshots in `docs/images/`, 2–8 catalog cards 960×600 JPG under 100 KB, dashboard first | Pass | 8 screenshots (85–149 KB); 6 cards in `docs/catalog/` (47–76 KB), overview first |
| Landing page: own identity, problem-first headline, captions, matching alt text, disclaimer, docs links, no CDN | Pass | Alt-text figures checked against the captured data |
| `docs/.nojekyll` and JS/CSS 200 on the live site | Pass | On the fork's Pages; re-check after Pages is switched to `main` `/docs` on the original repo |
| Briefs folder kept out of the repo | Pass | |

## CONTRIBUTING Musts

| Must | Result |
|---|---|
| Business problem first, one industry (Payments) and function (Operations) | Pass |
| Public repo `sfguide-<topic>`, Apache 2.0 `LICENSE` | Pass (unchanged) |
| GitHub Pages enabled (`.nojekyll` for `_` folders) | Pass on the fork; **owner action** after merge: set Pages to `main` `/docs` (redirects cover the gap) |
| Landing page: problem and outcome first, screenshots of the running app, captions naming the capability, alt text, capability named per step, disclaimer, repo and docs links | Pass |
| No Snowflake logo files or trademarked imagery; no internal sales language | Pass |
| End-user app with a real workflow (navigation, drill-downs, key action) | Pass |
| No-account mode, `setup: local`; simulated AI labeled | Pass (local Streamlit Sample mode + hosted `/try/`) |
| Live mode against Snowflake on synthetic data | Pass |
| Synthetic data only; self-contained setup (own DB, XSMALL WH, short auto-suspend); cleanup removes everything | Pass |
| No credentials, keys, account identifiers or internal hostnames in code, screenshots, output or history | Pass for credentials, keys, identifiers and hostnames. One user name inside a local path in three historical `.pyc` blobs (see above) |
| User names redacted in captured output | Pass (captures contain no user names) |
| No customer names, data or identifiable logic; no deals or internal programs; GA or labeled Preview features | Pass. Coined merchant names replaced v1 names that matched real firms; AI prompts forbid real company names, and captured AI text was scanned |
| README: prerequisites, run steps, objects table, cost and time, limitations, Customize with Cortex Code, owner and review date, license and as-is disclaimer | Pass |
| Outcomes as possibilities; synthetic results qualified | Pass |

## CONTRIBUTING Shoulds

| Should | Result |
|---|---|
| Template repository | Skipped: a setting on the owner's repo |
| Repo description and topics | Skipped: owner's repo settings |
| Several screenshots / short video | Screenshots pass (8); video skipped (optional) |
| Prerequisites, time and cost near the top of the landing page | Pass |
| Phone width and dark mode on the landing page | Pass |
| No trackers; no CDN | Pass (font self-hosted) |
| Sample/Live switch in the header; setup steps when no connection; hosted switch points to the live guide | Pass |
| Realistic AI delays with truthful steps | Pass |
| Capability badge on each component | Pass |
| Least-privilege role | Pass |
| Edition notes | Pass (Standard Edition is enough) |
| "Example" wording, short sentences, acronyms defined | Pass |

## Not verified this round

- `sql/setup_cfpb.sql` (real CFPB benchmark): the test account has no CFPB data mounted, so it was written but not run.
- The deployed Streamlit in Snowflake app was created on the warehouse runtime with the pinned packages, but not opened in Snowsight (no browser sign-in in this environment). Its Live calls (SEMANTIC_VIEW, AI_COMPLETE, DATA_AGENT_RUN) were run inside an owner's-rights procedure, the same restriction the warehouse runtime applies, and all succeeded. The same code ran end to end through Snowpark locally.
