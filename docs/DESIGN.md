# Design: Chargeback & Dispute Intelligence

The app and the landing page share one product name, **Chargeback & Dispute Intelligence**. The
processor that uses it, **Halvane Payments**, is fictional, and so is every merchant in the data. No domain
or company with that processor name turned up when this was written (November 2026).

## Audience and voice

Dispute-operations analysts, chargeback managers and payments risk leads at a card processor or
acquirer. They live in reason codes, deadlines and win rates, and they need to explain a spike to
a merchant or a CFO in one page.

Voice: a calm case clerk. Short, factual labels ("Disputes filed", "Won after representment"),
reason codes always shown with their network ("Visa 10.4"), numbers before adjectives, and every
AI sentence traceable to a row of the fact pack. Never "likely", "around" or "about": the
verifier fails a note that hedges.

## Logo mark

A rounded docket tab in harbor teal with a return arrow (the money coming back) and a jade check
(the rebuttal held). Inline SVG, used in the app header and on the landing page:

```svg
<svg viewBox="0 0 32 32" aria-hidden="true">
  <rect width="32" height="32" rx="9" fill="#0C3B3E"/>
  <path d="M22 11h-9.5a4.5 4.5 0 0 0 0 9H15" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round"/>
  <path d="M15.5 8.5 12.5 11l3 2.5" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="m17.5 20.5 2.3 2.3 4.7-5" fill="none" stroke="#3FD3A1" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

## Direction: "the dispute docket"

A court docket for chargebacks: a dark harbor-teal masthead with **top navigation** (not a
sidebar), a cool fog canvas, and white "docket cards" whose 3 px left rule carries the status
color. Status always reads the same way everywhere: **jade = won**, **rust = lost**,
**indigo = pre-arbitration**, **slate = open**. Amounts use tabular figures so columns line up.

### Palette (light; tokens in `app/.streamlit/config.toml`, `app/theme.css` and `docs/try/app.css`)

| Token | Hex | Use |
|---|---|---|
| `masthead` | `#0C3B3E` | Top bar, logo square, landing hero band |
| `masthead-2` | `#134A4E` | Active nav tab, hover on the bar |
| `canvas` | `#EDF1F2` | Page background (cool fog) |
| `paper` | `#FFFFFF` | Cards, tables, dialogs |
| `paper-2` | `#F5F8F8` | Table headers, insets, code |
| `line` | `#D3DCDD` | Borders, gridlines |
| `ink` | `#102326` | Body text |
| `muted` | `#4E6064` | Secondary text (AA on canvas and paper) |
| `primary` | `#11757B` | Buttons, links, focus ring, Consumer Disputes series |
| `won` / `won-bg` | `#11795B` / `#DDF3EA` | Won pills, positive trends |
| `lost` / `lost-bg` | `#A33A12` / `#FBE5DA` | Lost pills, Fraud series, negative trends |
| `prearb` / `prearb-bg` | `#4B4FA6` / `#E6E7F7` | Pre-arbitration pills |
| `open` / `open-bg` | `#55606B` / `#ECEEF0` | Open pills |
| `gold` | `#7A6A2E` | Processing Errors series |
| `bench` | `#6B5512` | CFPB complaint benchmark line (dashed) |
| `ai` | `#0E6E7E` | AI panels, "Sample AI response" label, streaming caret |
| `jade-glow` | `#3FD3A1` | Logo check, verdict stamp on the dark masthead only |

The landing page adds a dark scheme (`prefers-color-scheme: dark`): canvas `#0A1C1E`, paper
`#102A2D`, ink `#E4EEEE`, muted `#9DB3B5`, primary `#4FC3C9`. The Streamlit app stays light: its
theme is set once in `config.toml`, and Streamlit in Snowflake viewers can switch the built-in
dark theme from the app menu.

Contrast was checked with `scripts/check_contrast.py` (WCAG AA, 4.5:1 for text): every text
token passes on `canvas`, `paper` and its own pill background.

### Typography

- **Sora** (OFL, self-hosted in `docs/fonts/` and `app/static/`) for headings, KPI values and
  the wordmark. No other pack in the catalog uses it.
- The system UI stack (`-apple-system, "Segoe UI", Roboto, sans-serif`) for body text, so the
  Streamlit in Snowflake paste-in path still looks right without font files.
- `font-variant-numeric: tabular-nums` on every amount, rate and count.

### Layout model and density

- Top navigation in the masthead: **Overview · Reason codes · Merchants · Chargeback notes ·
  Ask the desk**. A user/role chip ("Dispute analyst · Halvane Payments") and the environment
  badge (Sample or Live) sit on the right.
- Content max width 1280 px, 12-column feel: KPI strip of five tiles, then a 2:1 chart/insight
  row, then tables. Compact density (13–14 px table text, 8 px row padding).
- Detail opens in a **dialog panel** (Streamlit `st.dialog`, a right-side drawer in the hosted
  example) with the reason code's trend, its network/category split and its root cause.
- At 390 px every grid collapses to one column, the nav scrolls horizontally inside the bar,
  and wide tables scroll inside their own card.

### Charts

Altair in the app, hand-drawn SVG in the hosted example; both follow the same rules:
- Monthly stacked area by reason category (rust / teal / gold) with the CFPB benchmark as a
  dashed ochre line on its own right axis, and a soft band behind Nov–Jan labeled "Holiday".
- Horizontal bars for dollars lost by reason code, colored by category.
- A category × month heatmap of chargeback rate in basis points on a fog-to-teal scale.
- Thin 1 px gridlines in `line`, no chart borders, tooltips on every mark, legends on top.

### Motion

- Cards fade up 8 px on first render (180 ms, `animation-fill-mode: backwards`).
- KPI counts tick up once with a CSS `@property` counter (900 ms); dollar values fade in.
- Skeleton shimmer blocks while a Live query runs.
- AI notes: a staged checklist (fact pack → draft → verify) and a word-by-word streaming reveal
  with a blinking teal caret. A verdict stamp ("Verified" in jade, "Needs review" in rust)
  presses in with a short scale animation.
- Everything respects `prefers-reduced-motion`.

## How it differs from the live catalog

Looked at the landing pages and Try apps of Auto Finance Portfolio Analytics, Workforce
Intelligence, Complaints Intelligence (Tallowmark), Continuous Control Testing (Tallyward),
Loan File Review (Lintora), Market Data Discovery (Tidemere), Trade Reporting Validation
(Cadrel), Client Account Views (Quillstone), Governed Context Layer (Veritome) and Loss Triangle
Analysis. What this pack avoids:

- **Palette:** no Snowflake blue/navy template, no burgundy (Tallowmark), no vermilion-on-paper
  (Tallyward), no cobalt and highlighter yellow (Lintora), no navy and pink (Tidemere), no amber
  on black (Cadrel, Quillstone), no lime on graphite (Veritome), no purple night (Loss
  Triangle), no cream and plum (Workforce). Harbor teal with jade/rust status is unused.
- **Layout:** almost every pack uses a left sidebar. This app uses a top-nav masthead and
  docket cards with a status rule.
- **Hero:** no dashboard screenshot hero, no gradient blob, no terminal mock. The landing hero
  is a stack of perforated "chargeback tickets" drawn in CSS, with a verdict stamp on top.
- **Type:** Sora is not used by any other pack (others use Inter, Space Grotesk, IBM Plex,
  Bricolage Grotesque, Geist, Fraunces, Manrope, Public Sans).
