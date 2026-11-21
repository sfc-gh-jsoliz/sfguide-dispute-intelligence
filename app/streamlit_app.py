"""Chargeback & Dispute Intelligence (Streamlit).

One file, so it can be pasted into a Streamlit in Snowflake app as-is.
- Live mode: Snowpark. Inside Streamlit in Snowflake it uses the app's session; locally it
  uses key-pair auth from environment variables (see README, "Run locally in Live mode").
- Sample mode: bundled JSON in app/sample/, captured from a Live run of sql/setup.sql by
  scripts/capture_sample.py. Simulated AI waits 4-8 s and is labeled "Sample AI response".
There is no silent fallback: if a Live call fails, the error is shown.
"""
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

SCHEMA = "SNOWPACK_DISPUTE_INTEL.CORE"
SV = f"{SCHEMA}.DISPUTE_SV"
AGENT = f"{SCHEMA}.DISPUTE_AGENT"
MODEL = "claude-sonnet-4-5"
ROLE = "SNOWPACK_DISPUTE_INTEL_ROLE"
WAREHOUSE = "SNOWPACK_DISPUTE_INTEL_WH"
AS_OF = "30 Jun 2026"
SAMPLE_DIR = Path(__file__).parent / "sample"

C = {  # design tokens (docs/DESIGN.md)
    "masthead": "#0C3B3E", "canvas": "#EDF1F2", "paper": "#FFFFFF", "paper2": "#F5F8F8",
    "line": "#D3DCDD", "ink": "#102326", "muted": "#4E6064", "primary": "#11757B",
    "won": "#11795B", "lost": "#A33A12", "prearb": "#4B4FA6", "open": "#55606B",
    "gold": "#7A6A2E", "bench": "#6B5512", "ai": "#0E6E7E",
}
CATEGORY_NAMES = {"DIGITAL": "Digital Goods", "TRAVEL": "Travel", "RETAIL": "Retail", "GROCERY": "Grocery"}
CAT_COLORS = {"Fraud": C["lost"], "Consumer Disputes": C["primary"], "Processing Errors": C["gold"]}
SAMPLE_QUESTIONS = [
    "How did chargeback volume in Nov-Dec compare to the prior 3 months, by reason category?",
    "What is our win rate by reason code, and where are we losing the most dollars?",
    "How do our dispute trends compare to CFPB complaint volume for the same period?",
]
SCOPES = {
    "holiday": "Holiday spike: Nov 2025-Jan 2026 vs Aug-Oct 2025",
    "book": "Book review: first vs latest month (Jul 2024 vs Jun 2026)",
}
HEDGE_LINE = "\n\nFraud disputes likely rose around 40% and could keep climbing into next season."


# ----------------------------------------------------------------------------
# Data layer: one function per op, Live (Snowpark) or Sample (bundled JSON)
# ----------------------------------------------------------------------------
def _sis_session():
    try:
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except Exception:
        return None


def _env_ready():
    return all(os.environ.get(k) for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH"))


@st.cache_resource(show_spinner=False)
def _local_session():
    from snowflake.snowpark import Session
    return Session.builder.configs({
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "authenticator": "SNOWFLAKE_JWT",
        "private_key_file": os.path.expanduser(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]),
        "role": os.environ.get("SNOWFLAKE_ROLE", ROLE),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", WAREHOUSE),
        "database": "SNOWPACK_DISPUTE_INTEL",
        "schema": "CORE",
    }).create()


def live_session():
    return _sis_session() or (_local_session() if _env_ready() else None)


def _rows(sess, q, params=None):
    df = sess.sql(q, params=params or []).to_pandas()
    df.columns = [c.lower() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
        elif str(df[c].dtype).startswith("datetime"):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    return json.loads(df.to_json(orient="records", date_format="iso"))


def live_monthly(sess):
    return _rows(sess, f"""SELECT * FROM SEMANTIC_VIEW({SV}
        METRICS total_disputes, total_dispute_usd, total_won, total_resolved, total_lost_usd,
                total_friendly_fraud, cfpb_complaints
        DIMENSIONS month_end, reason_category) ORDER BY month_end, reason_category""")


def live_category_month(sess):
    return _rows(sess, f"""SELECT * FROM SEMANTIC_VIEW({SV}
        METRICS total_disputes, total_dispute_usd, total_lost_usd, processed_txn
        DIMENSIONS merchant_category, category_name, month_end) ORDER BY month_end, merchant_category""")


def live_reason_monthly(sess):
    return _rows(sess, f"""SELECT * FROM SEMANTIC_VIEW({SV}
        METRICS total_disputes, total_dispute_usd, total_won, total_resolved, total_lost_usd
        DIMENSIONS network, reason_code, reason_name, reason_category, month_end)
        ORDER BY reason_code, month_end""")


def live_reason_by_category(sess):
    return _rows(sess, f"""SELECT * FROM SEMANTIC_VIEW({SV}
        METRICS total_disputes, total_won, total_resolved, total_lost_usd
        DIMENSIONS reason_code, category_name) ORDER BY reason_code, category_name""")


def live_reason_dim(sess):
    return _rows(sess, f"""SELECT reason_code, network, reason_category, reason_name, description,
        typical_root_cause, is_friendly_fraud FROM {SCHEMA}.DISPUTE_REASON_CODE ORDER BY reason_code""")


def live_merchants(sess):
    return _rows(sess, f"""SELECT f.merchant_id, f.merchant_name, m.mcc, f.merchant_category, f.network, f.reason_code, f.status,
        COUNT(*) AS disputes, ROUND(SUM(f.dispute_amount), 2) AS dispute_usd
        FROM {SCHEMA}.DISPUTE_FACT f JOIN {SCHEMA}.DISPUTE_MERCHANT m USING (merchant_id)
        GROUP BY ALL ORDER BY 1, 6, 7""")


def live_merchant_detail(sess, merchant_id):
    mid = int(merchant_id)
    monthly = _rows(sess, f"""SELECT month_end, reason_code, COUNT(*) AS disputes FROM {SCHEMA}.DISPUTE_FACT
        WHERE merchant_id = ? GROUP BY ALL ORDER BY month_end""", [mid])
    inflight = _rows(sess, f"""SELECT dispute_id, network, reason_code, date_filed, respond_by, status,
        dispute_amount FROM {SCHEMA}.DISPUTE_FACT WHERE merchant_id = ? AND status IN ('open', 'pre-arb')
        ORDER BY respond_by, dispute_id LIMIT 25""", [mid])
    return {"monthly": monthly, "inflight": inflight}


def live_reports(sess):
    return _rows(sess, f"""SELECT run_id, subject, scope, status, edits_applied, residual_hedges, edits,
        report_md, fact_pack, latency_ms, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created_at
        FROM {SCHEMA}.DISPUTE_REPORTS ORDER BY created_at DESC LIMIT 24""")


def live_fact_pack(sess, scope):
    if scope == "holiday":
        rows = _rows(sess, f"""WITH m AS (
            SELECT reason_category, month_end, SUM(dispute_count) d, SUM(total_dispute_amount) usd,
                   SUM(won_count) w, SUM(resolved_count) r, SUM(friendly_fraud_count) ff, MAX(cfpb_complaint_count) c
            FROM {SCHEMA}.DISPUTE_BENCHMARK WHERE month_end BETWEEN '2025-08-31' AND '2026-01-31' GROUP BY 1, 2)
          SELECT reason_category, IFF(month_end >= '2025-11-30', 'Nov 2025-Jan 2026', 'Aug-Oct 2025') AS period,
                 ROUND(AVG(d)) AS avg_monthly_disputes, ROUND(AVG(usd)) AS avg_monthly_dispute_usd,
                 ROUND(SUM(w) / NULLIF(SUM(r), 0), 3) AS win_rate, ROUND(SUM(ff) / NULLIF(SUM(d), 0), 3) AS friendly_fraud_rate,
                 ROUND(AVG(c)) AS avg_monthly_cfpb_complaints
          FROM m GROUP BY 1, 2 ORDER BY 1, 2 DESC""")
    else:
        rows = _rows(sess, f"""WITH w AS (SELECT MIN(month_end) a, MAX(month_end) z FROM {SCHEMA}.DISPUTE_BENCHMARK)
          SELECT s.reason_category, s.month_end::string AS month, SUM(s.dispute_count) AS dispute_count,
                 ROUND(SUM(s.total_dispute_amount)) AS dispute_usd,
                 ROUND(SUM(s.won_count) / NULLIF(SUM(s.resolved_count), 0), 3) AS win_rate,
                 ROUND(SUM(s.friendly_fraud_count) / NULLIF(SUM(s.dispute_count), 0), 3) AS friendly_fraud_rate,
                 MAX(s.cfpb_complaint_count) AS cfpb_complaints
          FROM {SCHEMA}.DISPUTE_BENCHMARK s JOIN w ON s.month_end IN (w.a, w.z) GROUP BY 1, 2 ORDER BY 1, 2""")
    return [{"id": f"F{i + 1}", **r} for i, r in enumerate(rows)]


def _draft_prompt(scope, fp):
    compare = ("compare Nov 2025-Jan 2026 (holiday) with Aug-Oct 2025 per reason category; avg_monthly_* are monthly averages; "
               "call it 'holiday vs the prior three months', never month-over-month"
               if scope == "holiday" else "compare the latest month (2026-06-30) with the earliest (2024-07-31) per reason category, showing earliest -> latest; "
               "the latest month still has open disputes, so say its win rate covers resolved disputes only")
    return (
        "You are a payments dispute-ops analyst at a card processor. Write a concise chargeback note using ONLY the FACTS JSON.\n"
        "DATA RULES: use only numbers in FACTS, copy exactly; win_rate and friendly_fraud_rate are fractions (0-1), express as %; "
        "dollars are USD, express $M/$K; cfpb complaint figures are a monthly market-wide benchmark (never sum them across reason categories); "
        f"{compare}; no estimates, no hedging, no outside benchmarks; missing = n/d. " + ALLOWED + " "
        "After each figure, cite the fact id in square brackets, e.g. [F2]. Do not name any real company, bank or card network partner.\n"
        "OUTPUT markdown starting with '# ', a one-line takeaway (which reason categories drove disputes), a table "
        "(reason category | disputes | disputed $ | win rate | friendly-fraud rate), 3 bullets, ending with '## Data Coverage'."
        f"\n\nFACTS: {json.dumps(fp)}"
    )


def _complete(sess, prompt):
    """AI_COMPLETE returns its text as a JSON-encoded string; decode it."""
    raw = sess.sql("SELECT AI_COMPLETE(?, ?)", params=[MODEL, prompt]).collect()[0][0] or ""
    try:
        v = json.loads(raw)
        return v if isinstance(v, str) else raw
    except ValueError:
        return raw


ALLOWED = ("Allowed and NOT a problem: rounding dollars to $K/$M, rounding rates to one decimal %, percentage changes "
           "computed from two facts if correct to the nearest whole percent, win-rate changes stated in percentage points, citation tags like [F2], and saying that the "
           "latest month's win rate covers resolved disputes only (recent disputes are still open).")


def _last_json(raw):
    """The verifier sometimes re-checks itself and writes several JSON objects; its final one is the verdict."""
    dec, found, i = json.JSONDecoder(), None, raw.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(raw, i)
            if isinstance(obj, dict) and "status" in obj:
                found = obj
            i = raw.find("{", end)
        except ValueError:
            i = raw.find("{", i + 1)
    return found


def _verify(sess, fp, draft):
    vp = (
        "You are a fact-checker. Compare the DRAFT against the FACTS JSON (the only allowed source). " + ALLOWED + " "
        "Flag only numbers or claims that FACTS do not support, and hedge words like likely/approximately/around/could. "
        "Return ONLY a JSON object, no code fences, with keys status ('verified' if nothing is flagged, else 'needs_review'), "
        "residual_hedges (int), edits (array of short strings, one per real problem; never list items you found acceptable; empty if verified).\n\n"
        f"FACTS: {json.dumps(fp)}\n\nDRAFT:\n{draft}"
    )
    v = None
    for _ in range(2):
        v = _last_json(_complete(sess, vp))
        if v is not None:
            break
    if v is None:
        v = {"status": "needs_review", "residual_hedges": None, "edits": ["Verifier output could not be parsed"]}
    v["edits"] = [str(x) for x in (v.get("edits") or [])]
    v["status"] = "verified" if v.get("status") == "verified" and not v["edits"] else "needs_review"
    return v


def live_generate(sess, scope):
    t0 = time.time()
    fp = live_fact_pack(sess, scope)
    t1 = time.time()
    draft = _complete(sess, _draft_prompt(scope, fp)).strip()
    t2 = time.time()
    v = _verify(sess, fp, draft)
    t3 = time.time()
    latency = int((t3 - t0) * 1000)
    sess.sql(
        f"""INSERT INTO {SCHEMA}.DISPUTE_REPORTS (subject, scope, draft_md, report_md, status, edits_applied, residual_hedges,
            edits, fact_pack, latency_ms) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""",
        params=[SCOPES[scope].split(":")[0], scope, draft, draft, v["status"], len(v["edits"]), v.get("residual_hedges"),
                json.dumps(v["edits"]), json.dumps(fp), latency],
    ).collect()
    return {"scope": scope, "fact_pack": fp, "draft": draft, "verdict": v, "latency_ms": latency,
            "timings_ms": {"fact_pack": int((t1 - t0) * 1000), "draft": int((t2 - t1) * 1000), "verify": int((t3 - t2) * 1000)}}


def live_reverify(sess, scope, draft):
    t0 = time.time()
    fp = live_fact_pack(sess, scope)
    v = _verify(sess, fp, draft)
    return {"verdict": v, "latency_ms": int((time.time() - t0) * 1000)}


def live_ask(sess, question):
    t0 = time.time()
    req = json.dumps({"messages": [{"role": "user", "content": [{"type": "text", "text": question}]}]})
    raw = sess.sql("SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?)", params=[AGENT, req]).collect()[0][0]
    content = json.loads(raw).get("content", [])
    last_tool = max([i for i, b in enumerate(content) if b.get("type") in ("tool_use", "tool_result")] or [-1])
    text, tables, sql = [], [], []
    for b in content:
        if b.get("type") == "tool_use" and b["tool_use"].get("input", {}).get("sql"):
            sql.append(b["tool_use"]["input"]["sql"])
    for b in content[last_tool + 1:]:
        if b.get("type") == "text":
            text.append(b["text"])
        elif b.get("type") == "table":
            rs = b["table"].get("result_set", {})
            cols = [c.get("name") for c in rs.get("resultSetMetaData", {}).get("rowType", [])]
            tables.append({"title": b["table"].get("title", ""), "columns": cols, "rows": rs.get("data", [])})
    if not text and not tables:
        raise RuntimeError("The Cortex Agent returned no answer. Check that sql/setup.sql created DISPUTE_AGENT.")
    return {"question": question, "text": "".join(text).strip(), "tables": tables, "sql": sql[-1] if sql else "",
            "latency_ms": int((time.time() - t0) * 1000)}


LIVE_OPS = {
    "monthly": live_monthly, "category_month": live_category_month, "reason_monthly": live_reason_monthly,
    "reason_by_category": live_reason_by_category, "reason_dim": live_reason_dim, "merchants": live_merchants,
    "merchant_detail": live_merchant_detail, "reports": live_reports, "fact_pack": live_fact_pack,
}


def sample_key(name, *args):
    return "_".join([name] + [re.sub(r"[^a-z0-9]+", "-", str(a).lower()).strip("-")[:40] for a in args])


def load_sample(name, *args):
    p = SAMPLE_DIR / f"{sample_key(name, *args)}.json"
    if not p.exists():
        raise FileNotFoundError(f"No sample file {p.name}. Run scripts/capture_sample.py against a Live setup.")
    return json.loads(p.read_text())


@st.cache_data(ttl=600, show_spinner=False)
def _cached_live(name, *args):
    return LIVE_OPS[name](live_session(), *args)


def op(name, *args):
    if st.session_state.get("mode") == "Live":
        return _cached_live(name, *args)
    return load_sample(name, *args)


# ----------------------------------------------------------------------------
# Formatting and small HTML helpers
# ----------------------------------------------------------------------------
def month_start(col):
    """Plot months at the 1st so bars and points sit on their own month tick (month_end would drift to the next)."""
    return pd.to_datetime(col).dt.to_period("M").dt.to_timestamp()


def usd(v):
    v = float(v or 0)
    return f"${v / 1e6:.2f}M" if abs(v) >= 1e6 else f"${v / 1e3:.0f}K" if abs(v) >= 1e3 else f"${v:,.0f}"


def pct(v, d=1):
    return "n/d" if v is None or pd.isna(v) else f"{float(v) * 100:.{d}f}%"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pill(label, kind):
    return f'<span class="rb-pill rb-{kind}">{esc(label)}</span>'


STATUS_PILL = {"won": ("Won", "won"), "lost": ("Lost", "lost"), "pre-arb": ("Pre-arbitration", "prearb"), "open": ("Open", "open")}


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def skeleton(n=3, h=86):
    return "".join(f'<div class="rb-skel" style="height:{h}px"></div>' for _ in range(n))


def kpi_tile(label, value, note, trend=None, good_when_up=True, count=None):
    arrow = ""
    if trend is not None:
        up = trend >= 0
        kind = "won" if up == good_when_up else "lost"
        arrow = f'<span class="rb-trend rb-t-{kind}">{"&#9650;" if up else "&#9660;"} {abs(trend) * 100:.0f}%</span>'
    if count is not None:  # odometer: each digit ticks up from 0, separators stay put
        digits = "".join(f'<span class="rb-count" style="--n:{ch}"></span>' if ch.isdigit() else esc(ch) for ch in value)
        val = f'<span aria-label="{esc(value)}">{digits}</span>'
    else:
        val = esc(value)
    return (f'<div class="rb-kpi"><div class="rb-kpi-l">{esc(label)}</div><div class="rb-kpi-v">{val}</div>'
            f'<div class="rb-kpi-n">{arrow}<span>{esc(note)}</span></div></div>')


def badge(text):
    html(f'<div class="rb-powered"><span class="rb-dot"></span>{esc(text)}</div>')


def live_error(e):
    st.error(f"Live call failed: {e}", icon=":material/error:")
    st.caption("Live mode never falls back to sample data. Check that sql/setup.sql ran and the key-pair settings "
               "in the README are set, or switch to Sample.")
    st.stop()


def guarded(name, *args):
    try:
        return op(name, *args)
    except FileNotFoundError as e:
        st.warning(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001 - shown to the reader, never swallowed
        live_error(e)


def with_skeleton(name, *args, n=2, h=90):
    ph = st.empty()
    if st.session_state.get("mode") == "Live":
        ph.markdown(f'<div class="rb-skel-wrap">{skeleton(n, h)}</div>', unsafe_allow_html=True)
    data = guarded(name, *args)
    ph.empty()
    return data


def chart_config(ch):
    return (ch.configure(font="-apple-system, Segoe UI, Roboto, sans-serif", background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=C["muted"], titleColor=C["muted"], gridColor=C["line"], domainColor=C["line"],
                            tickColor=C["line"], labelFontSize=11, titleFontSize=11, titleFontWeight=500)
            .configure_legend(orient="top", labelColor=C["ink"], titleColor=C["muted"], labelFontSize=11, symbolSize=80,
                              titleFontSize=11)
            .configure_title(color=C["ink"], fontSize=13, anchor="start"))


def stream_words(text, wps=60):
    for tok in re.split(r"(\s+)", text):
        yield tok
        if tok.strip():
            time.sleep(1 / wps)


def ai_label(latency_ms=None):
    if st.session_state.get("mode") == "Live":
        tail = f" · {latency_ms / 1000:.1f} s measured" if latency_ms else ""
        html(f'<div class="rb-ai-label rb-ai-live">Live Cortex AI response{tail}</div>')
    else:
        html('<div class="rb-ai-label">Sample AI response · captured from a Live run, replayed with a simulated delay</div>')


def staged(steps, total_s=None):
    """Show staged progress. Sample: spread a 4-8 s delay over the steps. Live: caller runs the real call."""
    box = st.status(steps[0], expanded=True)
    if total_s is None:
        return box
    per = total_s / len(steps)
    for i, s in enumerate(steps):
        box.update(label=s)
        box.write(f":material/progress_activity: {s}")
        time.sleep(per * random.uniform(0.85, 1.15))
    return box


# ----------------------------------------------------------------------------
# Theme (CSS on top of .streamlit/config.toml; also works when pasted into Snowsight)
# ----------------------------------------------------------------------------
CSS = """
<style>
@font-face{font-family:Sora;src:url(app/static/Sora.woff2) format("woff2");font-weight:100 800;font-display:swap}
:root{--mast:#0C3B3E;--mast2:#134A4E;--canvas:#EDF1F2;--paper:#FFFFFF;--paper2:#F5F8F8;--line:#D3DCDD;--ink:#102326;
--muted:#4E6064;--primary:#11757B;--won:#11795B;--wonbg:#DDF3EA;--lost:#A33A12;--lostbg:#FBE5DA;--prearb:#4B4FA6;
--prearbbg:#E6E7F7;--open:#55606B;--openbg:#ECEEF0;--ai:#0E6E7E}
html{overflow-x:clip}
.stApp{background:var(--canvas)}
header[data-testid="stHeader"]{background:var(--mast);border-bottom:1px solid #22585C;height:3.6rem}
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span, header[data-testid="stHeader"] p{color:#E4EEEE!important}
header[data-testid="stHeader"] button svg{fill:#E4EEEE;color:#E4EEEE}
[data-testid="stTopNavLinkContainer"] a, [data-testid="stTopNavLink"]{border-radius:8px}
[data-testid="stTopNavLink"]:hover{background:var(--mast2)!important}
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stTopNavLink"].active{background:var(--mast2)!important;box-shadow:inset 0 -2px 0 #3FD3A1}
[data-testid="stHeaderLogo"], [data-testid="stLogo"]{height:30px!important;max-height:30px!important}
.block-container{padding-top:4.6rem;max-width:1280px}
h1,h2,h3,.rb-kpi-v,.rb-h{font-family:Sora,-apple-system,"Segoe UI",sans-serif;letter-spacing:-.01em}
h1{font-size:1.55rem!important;font-weight:700!important;color:var(--ink)}
h3{font-size:1.02rem!important;font-weight:650!important}
.rb-fade{animation:rbUp .18s ease-out backwards}
@keyframes rbUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.rb-ctx{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;margin:.1rem 0 .2rem}
.rb-chip{display:inline-flex;align-items:center;gap:.4rem;background:var(--paper);border:1px solid var(--line);border-radius:999px;
padding:.22rem .7rem;font-size:.78rem;color:var(--ink);max-width:100%}
.rb-avatar{width:20px;height:20px;border-radius:50%;background:var(--mast);color:#fff;font-size:.62rem;display:inline-grid;place-items:center;font-weight:700}
.rb-env{font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:.68rem;border-radius:999px;padding:.25rem .6rem}
.rb-env-sample{background:#FFF1D6;color:#6B4A00;border:1px solid #E9C979}
.rb-env-live{background:var(--wonbg);color:var(--won);border:1px solid #9AD6BF}
.rb-sub{color:var(--muted);font-size:.9rem;margin:-.35rem 0 .7rem}
.rb-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.7rem;margin:.3rem 0 .9rem}
.rb-kpi{background:var(--paper);border:1px solid var(--line);border-left:3px solid var(--primary);border-radius:10px;padding:.75rem .85rem;
min-width:0;animation:rbUp .22s ease-out backwards;transition:box-shadow .15s,transform .15s}
.rb-kpi:hover{box-shadow:0 6px 18px rgba(12,59,62,.09);transform:translateY(-1px)}
.rb-kpi:nth-child(2){animation-delay:.04s}.rb-kpi:nth-child(3){animation-delay:.08s}.rb-kpi:nth-child(4){animation-delay:.12s}.rb-kpi:nth-child(5){animation-delay:.16s}
.rb-kpi-l{font-size:.72rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.rb-kpi-v{font-size:1.45rem;font-weight:700;color:var(--ink);margin-top:.15rem;font-variant-numeric:tabular-nums}
.rb-kpi-n{font-size:.74rem;color:var(--muted);margin-top:.15rem;display:flex;gap:.35rem;flex-wrap:wrap}
.rb-trend{font-weight:700}.rb-t-won{color:var(--won)}.rb-t-lost{color:var(--lost)}
@property --n{syntax:"<integer>";initial-value:0;inherits:false}
.rb-count{--n:0;counter-reset:n var(--n);animation:rbCount .9s ease-out backwards}
.rb-count::after{content:counter(n)}
@keyframes rbCount{from{--n:0}}
.rb-pill{display:inline-block;font-size:.72rem;font-weight:650;border-radius:999px;padding:.12rem .55rem;white-space:nowrap}
.rb-won{background:var(--wonbg);color:var(--won)}.rb-lost{background:var(--lostbg);color:var(--lost)}
.rb-prearb{background:var(--prearbbg);color:var(--prearb)}.rb-open{background:var(--openbg);color:var(--open)}
.rb-ai{background:#E2F1F3;color:var(--ai)}
.rb-powered{display:inline-flex;align-items:center;gap:.4rem;font-size:.72rem;color:var(--ai);background:#E2F1F3;border-radius:999px;
padding:.18rem .6rem;font-weight:600;max-width:100%;flex-wrap:wrap}
.rb-dot{width:7px;height:7px;border-radius:50%;background:var(--ai);box-shadow:0 0 0 3px rgba(14,110,126,.18)}
.rb-insight{border-left:3px solid var(--line);padding:.45rem .7rem;margin:.35rem 0;background:var(--paper2);border-radius:0 8px 8px 0;font-size:.86rem}
.rb-insight b{font-family:Sora,sans-serif}
.rb-i-lost{border-left-color:var(--lost)}.rb-i-won{border-left-color:var(--won)}.rb-i-gold{border-left-color:#7A6A2E}.rb-i-ai{border-left-color:var(--ai)}
[class*="st-key-card"]{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:1rem 1.05rem;min-width:0;
animation:rbUp .2s ease-out backwards}
.rb-skel{background:linear-gradient(90deg,#E3E9EA 25%,#F2F5F5 37%,#E3E9EA 63%);background-size:400% 100%;animation:rbShim 1.3s ease infinite;
border-radius:10px;margin:.4rem 0}
@keyframes rbShim{0%{background-position:100% 50%}100%{background-position:0 50%}}
.rb-ai-label{display:inline-block;font-size:.72rem;font-weight:700;color:#6B4A00;background:#FFF1D6;border:1px solid #E9C979;border-radius:6px;padding:.15rem .5rem;margin:.2rem 0 .5rem}
.rb-ai-live{color:var(--won);background:var(--wonbg);border-color:#9AD6BF}
.rb-stamp{display:inline-block;font-family:Sora,sans-serif;font-weight:800;letter-spacing:.08em;text-transform:uppercase;font-size:.82rem;
border:2.5px solid currentColor;border-radius:8px;padding:.25rem .7rem;transform:rotate(-3deg);animation:rbStamp .35s cubic-bezier(.2,1.6,.4,1) backwards}
.rb-stamp-ok{color:var(--won)}.rb-stamp-bad{color:var(--lost)}
@keyframes rbStamp{from{transform:scale(1.6) rotate(-3deg);opacity:0}}
.rb-note{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:1rem 1.2rem}
.rb-docket{background:var(--paper);border:1px solid var(--line);border-left:3px solid var(--won);border-radius:10px;padding:.7rem .85rem;margin-bottom:.4rem}
.rb-docket.bad{border-left-color:var(--lost)}
.rb-docket .t{font-family:Sora,sans-serif;font-weight:650;font-size:.92rem;margin:.25rem 0}
.rb-docket .s{color:var(--muted);font-size:.76rem}
.rb-table{width:100%;border-collapse:collapse;font-size:.82rem;font-variant-numeric:tabular-nums}
.rb-table th{background:var(--paper2);color:var(--muted);font-weight:600;text-align:left;padding:.4rem .5rem;border-bottom:1px solid var(--line);white-space:nowrap}
.rb-table td{padding:.38rem .5rem;border-bottom:1px solid #E6ECED;white-space:nowrap}
.rb-table td.n,.rb-table th.n{text-align:right}
.rb-scroll{position:relative;overflow-x:auto;max-width:100%}
.rb-empty{border:1.5px dashed var(--line);border-radius:12px;padding:1.6rem;text-align:center;color:var(--muted);background:var(--paper)}
.rb-note-md{font-size:.92rem}.rb-note-md p{margin:.35rem 0}.rb-note-md ul{margin:.3rem 0 .5rem 1.1rem;padding:0}
.rb-md-h1{font-family:Sora,sans-serif;font-weight:700;font-size:1.2rem;margin:.2rem 0 .5rem}
.rb-md-h2,.rb-md-h3{font-family:Sora,sans-serif;font-weight:650;font-size:.98rem;margin:.9rem 0 .35rem}
.rb-md td,.rb-md th{white-space:normal}
.rb-cite{font-size:.68rem;font-weight:700;color:var(--ai);background:#E2F1F3;border-radius:4px;padding:0 .25rem;margin-left:.1rem}
.stButton button[kind="primary"]{background:var(--primary);border-color:var(--primary)}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px}
[data-testid="stDialog"] [role="dialog"]{border-radius:14px}
@media (max-width:900px){.rb-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.block-container{padding-left:.8rem;padding-right:.8rem}}
@media (max-width:480px){.rb-kpi-v{font-size:1.2rem}.rb-chip{font-size:.72rem}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
"""


def _inline(t):
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\[(F\d+(?:\s*,\s*F\d+)*)\]",
                  lambda m: "".join(f'<span class="rb-cite">{x}</span>' for x in re.split(r"\s*,\s*", m.group(1))), t)


def cite(md):
    """Render the note's markdown (headings, tables, bullets, bold, [F#] citations) to HTML.
    Done by hand so citation chips survive inside tables and "$" is never read as math."""
    lines, out, i = esc(md).replace("$", "&#36;").split("\n"), [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|?$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body = "".join("<tr>" + "".join(f"<{'th' if j == 0 else 'td'}>{_inline(c)}</{'th' if j == 0 else 'td'}>" for c in r) + "</tr>"
                           for j, r in enumerate(rows))
            out.append(f'<div class="rb-scroll"><table class="rb-table rb-md">{body}</table></div>')
            continue
        if re.match(r"^[-*] ", ln):
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                items.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        h = re.match(r"^(#{1,3}) (.*)$", ln)
        if h:
            out.append(f'<div class="rb-md-h{len(h.group(1))}">{_inline(h.group(2))}</div>')
        elif ln.strip():
            out.append(f"<p>{_inline(ln)}</p>")
        i += 1
    return '<div class="rb-note-md">' + "".join(out) + "</div>"


# ----------------------------------------------------------------------------
# Shared frames
# ----------------------------------------------------------------------------
def monthly_df():
    df = pd.DataFrame(guarded("monthly"))
    df["month"] = month_start(df["month_end"])
    return df


def book_totals(df):
    t = df.groupby("month", as_index=False).agg(
        disputes=("total_disputes", "sum"), usd=("total_dispute_usd", "sum"), won=("total_won", "sum"),
        resolved=("total_resolved", "sum"), lost=("total_lost_usd", "sum"), ff=("total_friendly_fraud", "sum"),
        cfpb=("cfpb_complaints", "max"))
    t["holiday"] = t["month"].dt.month.isin([11, 12, 1])
    return t


def reason_table():
    rm = pd.DataFrame(guarded("reason_monthly"))
    dim = pd.DataFrame(guarded("reason_dim"))
    g = rm.groupby(["network", "reason_code", "reason_name", "reason_category"], as_index=False).agg(
        disputes=("total_disputes", "sum"), usd=("total_dispute_usd", "sum"), won=("total_won", "sum"),
        resolved=("total_resolved", "sum"), lost=("total_lost_usd", "sum"))
    g["win_rate"] = g["won"] / g["resolved"].where(g["resolved"] > 0)
    g = g.merge(dim[["reason_code", "typical_root_cause", "description", "is_friendly_fraud"]], on="reason_code", how="left")
    return rm, g.sort_values("disputes", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------
def page_overview():
    st.title("Chargeback overview")
    html(f'<p class="rb-sub">Halvane Payments dispute book · 24 months to {AS_OF} · benchmarked against monthly consumer complaints</p>')
    df = monthly_df()
    t = book_totals(df)
    cm = pd.DataFrame(guarded("category_month"))
    cm["month"] = month_start(cm["month_end"])
    proc = cm.groupby("month")["processed_txn"].sum()
    t = t.merge(proc.rename("processed").reset_index(), on="month")
    t["bps"] = t["disputes"] / t["processed"] * 1e4

    hol, other = t[t.holiday]["disputes"].mean(), t[~t.holiday]["disputes"].mean()
    last3, prev3 = t.tail(3), t.iloc[-6:-3]
    wr = t["won"].sum() / t["resolved"].sum()
    wr_trend = (last3.won.sum() / last3.resolved.sum()) / (prev3.won.sum() / prev3.resolved.sum()) - 1
    ffs = t["ff"].sum() / t["disputes"].sum()
    hol_bps, oth_bps = t[t.holiday]["bps"].mean(), t[~t.holiday]["bps"].mean()
    html('<div class="rb-kpis">' + "".join([
        kpi_tile("Disputes filed", f"{int(t.disputes.sum()):,}", f"Nov-Jan vs other months", hol / other - 1, False,
                 count=t.disputes.sum()),
        kpi_tile("Disputed amount", usd(t.usd.sum()), "24 months, all networks"),
        kpi_tile("Win rate", pct(wr), "won / resolved · last 3 vs prior 3 mo", wr_trend, True),
        kpi_tile("Dollars lost", usd(t.lost.sum()), f"{usd(last3.lost.sum())} in the last 3 months"),
        kpi_tile("Chargeback rate", f"{t.bps.mean():.0f} bps", f"holiday {hol_bps:.0f} vs {oth_bps:.0f} bps", hol_bps / oth_bps - 1, False),
    ]) + "</div>")

    left, right = st.columns([2.1, 1], gap="medium")
    with left.container(key="card_trend"):
        st.markdown("### Disputes by reason category, with the complaint benchmark")
        badge("Semantic View DISPUTE_SV · SEMANTIC_VIEW() query")
        area_src = df.rename(columns={"total_disputes": "Disputes", "reason_category": "Reason category"})
        bands = pd.DataFrame({"start": pd.to_datetime(["2024-10-16", "2025-10-16"]), "end": pd.to_datetime(["2025-01-16", "2026-01-16"]),
                              "label": ["Holiday", "Holiday"]})
        x = alt.X("month:T", title=None, axis=alt.Axis(format="%b %y", labelAngle=0, tickCount=8))
        band = alt.Chart(bands).mark_rect(color="#F3E9CC", opacity=.55).encode(x="start:T", x2="end:T")
        band_t = alt.Chart(bands).mark_text(align="left", dx=4, dy=-2, baseline="top", color=C["bench"], fontSize=10,
                                            fontWeight=600).encode(x="start:T", y=alt.value(4), text="label")
        area = alt.Chart(area_src).mark_area(opacity=.88, interpolate="monotone").encode(
            x=x, y=alt.Y("Disputes:Q", stack=True, title="Disputes filed"),
            color=alt.Color("Reason category:N", scale=alt.Scale(domain=list(CAT_COLORS), range=list(CAT_COLORS.values())),
                            legend=alt.Legend(title=None)),
            tooltip=[alt.Tooltip("month:T", format="%b %Y", title="Month"), "Reason category:N",
                     alt.Tooltip("Disputes:Q", format=","), alt.Tooltip("total_dispute_usd:Q", format="$,.0f", title="Disputed $")])
        line = alt.Chart(t.assign(series="CFPB complaints (right axis)")).mark_line(
            color=C["bench"], strokeDash=[5, 4], strokeWidth=2, point=alt.OverlayMarkDef(size=18, color=C["bench"])).encode(
            x=x, y=alt.Y("cfpb:Q", title="Complaints / month", axis=alt.Axis(titleColor=C["bench"])),
            tooltip=[alt.Tooltip("month:T", format="%b %Y", title="Month"), alt.Tooltip("cfpb:Q", format=",", title="Complaints")])
        ch = alt.layer(band, band_t, area, line).resolve_scale(y="independent").properties(height=300)
        st.altair_chart(chart_config(ch), width="stretch")
        st.caption("Complaint counts are a market-wide monthly signal, joined by month only and never summed with disputes.")
    _, rt = reason_table()
    with right.container(key="card_insights"):
        st.markdown("### What stands out")
        worst = rt.sort_values("win_rate").iloc[0]
        top_loss = rt.sort_values("lost", ascending=False).iloc[0]
        cat = cm.groupby("category_name").agg(d=("total_disputes", "sum"))
        cat["p"] = cm.groupby("category_name")["processed_txn"].sum()
        cat["bps"] = cat.d / cat.p * 1e4
        hi = cat.sort_values("bps", ascending=False)
        html(
            f'<div class="rb-insight rb-i-gold"><b>Holiday spike.</b> Nov-Jan averaged {hol:,.0f} disputes a month vs {other:,.0f} '
            f'in other months (+{(hol / other - 1) * 100:.0f}%).</div>'
            f'<div class="rb-insight rb-i-lost"><b>Hardest to win: {esc(worst.network.title())} {esc(worst.reason_code)}</b> '
            f'({esc(worst.reason_name)}) at {pct(worst.win_rate)} vs {pct(wr)} for the book.</div>'
            f'<div class="rb-insight rb-i-lost"><b>Most dollars lost: {esc(top_loss.reason_code)}</b>, {usd(top_loss.lost)} over 24 months.</div>'
            f'<div class="rb-insight rb-i-won"><b>{esc(hi.index[0])}</b> runs {hi.bps.iloc[0]:.0f} bps, '
            f'{hi.bps.iloc[0] / hi.bps.iloc[-1]:.1f}x {esc(hi.index[-1])}.</div>'
            '<div class="rb-insight rb-i-ai">Computed from the semantic view, not AI. Open <b>Chargeback notes</b> for a verified write-up.</div>')
        st.page_link(PAGES["notes"], label="Write a verified note", icon=":material/edit_note:")

    with st.container(key="card_lost"):
        st.markdown("### Dollars lost by reason code")
        src = rt.assign(label=rt.network.str.title() + " " + rt.reason_code + " · " + rt.reason_name)
        bars = alt.Chart(src).mark_bar(cornerRadiusEnd=4, height=16).encode(
            y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("lost:Q", title="Dollars lost (USD)", axis=alt.Axis(format="$.2s")),
            color=alt.Color("reason_category:N", scale=alt.Scale(domain=list(CAT_COLORS), range=list(CAT_COLORS.values())),
                            legend=alt.Legend(title=None)),
            tooltip=[alt.Tooltip("label:N", title="Reason code"), alt.Tooltip("lost:Q", format="$,.0f", title="Lost"),
                     alt.Tooltip("win_rate:Q", format=".1%", title="Win rate"), alt.Tooltip("disputes:Q", format=",")])
        st.altair_chart(chart_config(bars.properties(height=250)), width="stretch")


@st.dialog("Reason code", width="large")
def reason_drawer(code):
    rm, rt = reason_table()
    r = rt[rt.reason_code == code].iloc[0]
    book_wr = rt.won.sum() / rt.resolved.sum()
    kind = "lost" if r.win_rate < book_wr - .05 else "won"
    html(f'<h3 class="rb-h" style="margin:0">{esc(r.network.title())} {esc(code)} · {esc(r.reason_name)}</h3>'
         f'<div class="rb-ctx" style="margin:.4rem 0 .6rem">{pill(r.reason_category, "ai")} '
         f'{pill("Friendly fraud" if r.is_friendly_fraud else "Cardholder claim", "lost" if r.is_friendly_fraud else "open")} '
         f'{pill(("Below" if kind == "lost" else "At or above") + " book win rate", kind)}</div>'
         f'<p style="font-size:.88rem;margin:0 0 .2rem">{esc(r.description)}.</p>'
         f'<p style="font-size:.84rem;color:{C["muted"]}">Typical root cause: <b>{esc(r.typical_root_cause)}</b></p>')
    html('<div class="rb-kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">' + "".join([
        kpi_tile("Disputes", f"{int(r.disputes):,}", "24 months"), kpi_tile("Disputed", usd(r.usd), "USD"),
        kpi_tile("Win rate", pct(r.win_rate), f"book {pct(book_wr)}"), kpi_tile("Lost", usd(r.lost), "status lost")]) + "</div>")
    m = rm[rm.reason_code == code].copy()
    m["month"] = month_start(m["month_end"])
    m["win_rate"] = m.total_won / m.total_resolved.where(m.total_resolved > 0)
    base = alt.Chart(m).encode(x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %y", labelAngle=0)))
    ch = alt.layer(
        base.mark_bar(color=CAT_COLORS.get(r.reason_category, C["primary"]), opacity=.85, width=9).encode(
            y=alt.Y("total_disputes:Q", title="Disputes"),
            tooltip=[alt.Tooltip("month:T", format="%b %Y"), alt.Tooltip("total_disputes:Q", title="Disputes"),
                     alt.Tooltip("win_rate:Q", format=".1%", title="Win rate")]),
        base.mark_line(color=C["ink"], strokeWidth=1.6).encode(y=alt.Y("win_rate:Q", title="Win rate", axis=alt.Axis(format="%")))
    ).resolve_scale(y="independent").properties(height=200, title="Monthly disputes (bars) and win rate (line)")
    st.altair_chart(chart_config(ch), width="stretch")
    bc = pd.DataFrame(guarded("reason_by_category"))
    bc = bc[bc.reason_code == code].assign(win_rate=lambda d: d.total_won / d.total_resolved)
    rows = "".join(f'<tr><td>{esc(x.category_name)}</td><td class="n">{int(x.total_disputes):,}</td><td class="n">{pct(x.win_rate)}</td>'
                   f'<td class="n">{usd(x.total_lost_usd)}</td></tr>' for x in bc.itertuples())
    html('<div class="rb-scroll"><table class="rb-table"><tr><th>Merchant category</th><th class="n">Disputes</th>'
         f'<th class="n">Win rate</th><th class="n">Lost</th></tr>{rows}</table></div>')
    badge("Semantic View DISPUTE_SV")


def page_reasons():
    st.title("Reason codes")
    html('<p class="rb-sub">Every Visa and Mastercard reason code in the book. Select a row to open its detail panel.</p>')
    _, rt = reason_table()
    book_wr = rt.won.sum() / rt.resolved.sum()
    c1, c2, c3 = st.columns([1, 1.4, 1.2])
    nets = c1.pills("Network", ["VISA", "MASTERCARD"], selection_mode="multi", default=["VISA", "MASTERCARD"])
    cats = c2.pills("Reason category", list(CAT_COLORS), selection_mode="multi", default=list(CAT_COLORS))
    q = c3.text_input("Search", placeholder="e.g. recurring, 10.4", label_visibility="visible")
    f = rt[rt.network.isin(nets or []) & rt.reason_category.isin(cats or [])]
    if q:
        f = f[f.apply(lambda r: q.lower() in f"{r.reason_code} {r.reason_name} {r.typical_root_cause}".lower(), axis=1)]
    if f.empty:
        html('<div class="rb-empty">No reason codes match these filters. Clear a filter or the search box.</div>')
        return
    f = f.assign(status=f.win_rate.map(lambda w: "● Below book" if w < book_wr - .05 else "● At or above book"),
                 net=f.network.str.title(), usd_k=f.usd / 1e3, lost_k=f.lost / 1e3, win_pct=f.win_rate * 100)
    with st.container(key="card_reasons"):
        badge(f"Book win rate {pct(book_wr)} · rows from SEMANTIC_VIEW(DISPUTE_SV)")
        ev = st.dataframe(
            f[["net", "reason_code", "reason_name", "reason_category", "disputes", "usd_k", "win_pct", "lost_k", "status",
               "typical_root_cause"]],
            hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="reason_grid",
            column_config={
                "net": st.column_config.TextColumn("Network"),
                "reason_code": st.column_config.TextColumn("Code", width="small"),
                "reason_name": "Reason", "reason_category": "Category",
                "disputes": st.column_config.NumberColumn("Disputes", format="localized"),
                "usd_k": st.column_config.NumberColumn("Disputed", format="$%.0fK"),
                "win_pct": st.column_config.ProgressColumn("Win rate", min_value=0, max_value=100, format="%.1f%%"),
                "lost_k": st.column_config.NumberColumn("Lost", format="$%.0fK"),
                "status": st.column_config.TextColumn("Status"),
                "typical_root_cause": "Typical root cause",
            })
    sel = ev.selection.rows if ev else []
    pick = f.iloc[sel[0]].reason_code if sel else None
    if pick and st.session_state.get("_reason_open") != pick:
        st.session_state["_reason_open"] = pick
        reason_drawer(pick)
    elif not pick:
        st.session_state["_reason_open"] = None


def merchant_table():
    raw = pd.DataFrame(guarded("merchants"))
    g = raw.groupby(["merchant_id", "merchant_name", "mcc", "merchant_category"], as_index=False).agg(
        disputes=("disputes", "sum"), usd=("dispute_usd", "sum"))
    cnt = raw.pivot_table(index="merchant_id", columns="status", values="disputes", aggfunc="sum", fill_value=0)
    cnt = cnt.reindex(columns=["won", "lost", "open", "pre-arb"], fill_value=0).add_prefix("n_")
    lost_usd = raw[raw.status == "lost"].groupby("merchant_id")["dispute_usd"].sum().rename("lost")
    top = (raw.groupby(["merchant_id", "network", "reason_code"])["disputes"].sum().reset_index()
           .sort_values(["disputes", "reason_code"], ascending=[False, True]).drop_duplicates("merchant_id")
           .set_index("merchant_id")[["reason_code", "disputes"]].rename(columns={"disputes": "top_n"}))
    g = g.set_index("merchant_id").join(cnt).join(lost_usd).join(top).reset_index()
    g["lost"] = g["lost"].fillna(0)
    g["win_rate"] = g.n_won / (g.n_won + g.n_lost).where(g.n_won + g.n_lost > 0)
    g["top_share"] = g.top_n / g.disputes
    g["in_flight"] = g["n_open"] + g["n_pre-arb"]
    # Concentration: the reason code whose share at this merchant is furthest above the category's mix.
    mc = raw.groupby(["merchant_id", "merchant_category", "reason_code"])["disputes"].sum().reset_index()
    mc["share"] = mc.disputes / mc.groupby("merchant_id").disputes.transform("sum")
    cat = mc.groupby(["merchant_category", "reason_code"]).disputes.sum()
    cat = (cat / cat.groupby(level=0).transform("sum")).rename("cat_share").reset_index()
    mc = mc.merge(cat, on=["merchant_category", "reason_code"])
    mc["lift"] = mc.share / mc.cat_share
    hot = mc.sort_values(["lift", "reason_code"], ascending=[False, True]).drop_duplicates("merchant_id").set_index("merchant_id")
    g = g.join(hot[["reason_code", "share", "cat_share", "lift"]].rename(columns={"reason_code": "hot_code"}), on="merchant_id")
    g["category"] = g.merchant_category.map(CATEGORY_NAMES)
    return raw, g


def page_merchants():
    st.title("Merchants")
    html('<p class="rb-sub">Chargeback rate by merchant category and month, and every merchant in the book. Select a merchant '
         'to see its disputes in flight.</p>')
    cm = pd.DataFrame(guarded("category_month"))
    cm["month"] = month_start(cm["month_end"])
    cm["bps"] = cm.total_disputes / cm.processed_txn * 1e4
    with st.container(key="card_heat"):
        st.markdown("### Chargeback rate (bps of processed transactions)")
        heat = alt.Chart(cm).mark_rect(cornerRadius=3, stroke="#FFFFFF", strokeWidth=1.5).encode(
            x=alt.X("month:O", title=None, timeUnit="yearmonth", axis=alt.Axis(format="%b %y", labelAngle=-45)),
            y=alt.Y("category_name:N", title=None, axis=alt.Axis(labelLimit=220), sort=["Digital Goods & Subscriptions", "Travel & Hospitality",
                                                         "Retail & E-commerce", "Grocery & Essentials"]),
            color=alt.Color("bps:Q", scale=alt.Scale(range=["#EAF3F3", "#7FBDBF", "#11757B", "#0C3B3E"]),
                            legend=alt.Legend(title="bps", orient="right")),
            tooltip=[alt.Tooltip("month:T", format="%b %Y", title="Month"), alt.Tooltip("category_name:N", title="Category"),
                     alt.Tooltip("bps:Q", format=".1f", title="Chargeback bps"), alt.Tooltip("total_disputes:Q", title="Disputes"),
                     alt.Tooltip("processed_txn:Q", format=",", title="Processed txns")])
        st.altair_chart(chart_config(heat.properties(height=190)), width="stretch")
        badge("Semantic View DISPUTE_SV · processed volume is non-additive (MAX per category-month)")
    raw, g = merchant_table()
    names = list(CATEGORY_NAMES.values())
    cats = st.pills("Category", names, selection_mode="multi", default=names)
    f = g[g.category.isin(cats or [])].sort_values("lost", ascending=False).reset_index(drop=True)
    if f.empty:
        html('<div class="rb-empty">No merchants in the selected categories.</div>')
        return
    f["flag"] = f.apply(lambda r: f"● {r.hot_code}: {r.share:.0%} of disputes vs {r.cat_share:.0%} for the category"
                        if r.lift >= 2 else "● In line with category mix", axis=1)
    f["usd_k"], f["lost_k"], f["win_pct"] = f.usd / 1e3, f.lost / 1e3, f.win_rate * 100
    with st.container(key="card_merchants"):
        ev = st.dataframe(
            f[["merchant_name", "category", "mcc", "disputes", "usd_k", "win_pct", "lost_k", "in_flight", "flag"]],
            hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="merchant_grid",
            column_config={
                "merchant_name": "Merchant", "category": "Category", "mcc": st.column_config.TextColumn("MCC", width="small"),
                "disputes": st.column_config.NumberColumn("Disputes", format="localized"),
                "usd_k": st.column_config.NumberColumn("Disputed", format="$%.0fK"),
                "win_pct": st.column_config.ProgressColumn("Win rate", min_value=0, max_value=100, format="%.1f%%"),
                "lost_k": st.column_config.NumberColumn("Lost", format="$%.0fK"),
                "in_flight": st.column_config.NumberColumn("In flight", format="%d", help="Open or in pre-arbitration"),
                "flag": st.column_config.TextColumn("Concentration", width="large"),
            })
        st.caption("Merchant rows come from DISPUTE_FACT (the semantic view stops at merchant category).")
    sel = ev.selection.rows if ev else []
    pick = int(f.iloc[sel[0]].merchant_id) if sel else None
    if pick and st.session_state.get("_merchant_open") != pick:
        st.session_state["_merchant_open"] = pick
        merchant_drawer(pick, f[f.merchant_id == pick].iloc[0].to_dict())
    elif not pick:
        st.session_state["_merchant_open"] = None


@st.dialog("Merchant", width="large")
def merchant_drawer(mid, row):
    d = guarded("merchant_detail", mid)
    html(f'<h3 class="rb-h" style="margin:0">{esc(row["merchant_name"])}</h3>'
         f'<div class="rb-ctx" style="margin:.4rem 0 .6rem">{pill(row["category"], "ai")} {pill("MCC " + row["mcc"], "open")}'
         f' {pill(str(int(row["in_flight"])) + " in flight", "prearb")}</div>')
    html('<div class="rb-kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">' + "".join([
        kpi_tile("Disputes", f"{int(row['disputes']):,}", "24 months"), kpi_tile("Win rate", pct(row["win_rate"]), "won / resolved"),
        kpi_tile("Lost", usd(row["lost"]), "USD"), kpi_tile("Hot code", row["hot_code"], f"{row['share']:.0%} vs {row['cat_share']:.0%} category")]) + "</div>")
    m = pd.DataFrame(d["monthly"])
    m["month"] = month_start(m["month_end"])
    ch = alt.Chart(m).mark_bar().encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %y", labelAngle=0)), y=alt.Y("disputes:Q", stack=True, title="Disputes"),
        color=alt.Color("reason_code:N", title="Reason code", scale=alt.Scale(scheme="tealblues")),
        tooltip=[alt.Tooltip("month:T", format="%b %Y"), "reason_code:N", "disputes:Q"]).properties(height=190)
    st.altair_chart(chart_config(ch), width="stretch")
    st.markdown("**Disputes in flight** (respond-by is 30 days after filing)")
    inf = d["inflight"]
    if not inf:
        html('<div class="rb-empty">No open or pre-arbitration disputes for this merchant.</div>')
        return
    rows = "".join(
        f'<tr><td>D-{int(x["dispute_id"]):06d}</td><td>{esc(x["network"].title())} {esc(x["reason_code"])}</td><td>{esc(x["date_filed"])}</td>'
        f'<td>{esc(x["respond_by"])}</td><td>{pill(*STATUS_PILL[x["status"]])}</td><td class="n">{usd(x["dispute_amount"]) if x["dispute_amount"] >= 1000 else "$" + format(x["dispute_amount"], ",.2f")}</td></tr>'
        for x in inf)
    html('<div class="rb-scroll"><table class="rb-table"><tr><th>Dispute</th><th>Reason</th><th>Filed</th><th>Respond by</th>'
         f'<th>Status</th><th class="n">Amount</th></tr>{rows}</table></div>')
    st.caption(f"Showing up to 25 by respond-by date, as of {AS_OF}.")


def note_view(res, scope, key):
    v = res["verdict"]
    ok = v["status"] == "verified"
    html(f'<div style="margin:.3rem 0 .6rem"><span class="rb-stamp {"rb-stamp-ok" if ok else "rb-stamp-bad"}">'
         f'{"Verified" if ok else "Needs review"}</span>'
         f'<span style="margin-left:.8rem;font-size:.8rem;color:{C["muted"]}">residual hedges: {v.get("residual_hedges")} · '
         f'flagged: {len(v["edits"])}</span></div>')
    if v["edits"]:
        html('<div class="rb-insight rb-i-lost"><b>Verifier flags</b><ul style="margin:.2rem 0 0 1rem;padding:0">'
             + "".join(f"<li>{esc(e)}</li>" for e in v["edits"]) + "</ul></div>")


def run_note(scope):
    fp_preview = guarded("fact_pack", scope)
    steps = [f"Reading the dispute book through DISPUTE_SV (24 months, 9,960 disputes)…",
             f"Building the fact pack: {len(fp_preview)} rows, the note's only allowed numbers…",
             f"Drafting the note with AI_COMPLETE ({MODEL})…",
             "Verifying every figure against the fact pack and checking for hedges…",
             "Saving the note and verdict to DISPUTE_REPORTS…"]
    if st.session_state.mode == "Live":
        box = staged(steps)
        for s in steps:
            box.write(f":material/progress_activity: {s}")
        try:
            res = LIVE_OPS_AI["generate"](live_session(), scope)
        except Exception as e:  # noqa: BLE001
            box.update(label="Live call failed", state="error")
            live_error(e)
        box.update(label=f"Done in {res['latency_ms'] / 1000:.1f} s (fact pack {res['timings_ms']['fact_pack'] / 1000:.1f} s · "
                         f"draft {res['timings_ms']['draft'] / 1000:.1f} s · verify {res['timings_ms']['verify'] / 1000:.1f} s)",
                   state="complete", expanded=False)
        _cached_live.clear()
    else:
        res = load_sample("generate", scope)
        box = staged(steps, random.uniform(4, 8))
        box.update(label="Done (sample replay)", state="complete", expanded=False)
    st.session_state["note"] = {"scope": scope, "res": res, "fresh": True}


def page_notes():
    st.title("Chargeback notes")
    html('<p class="rb-sub">A one-page note for a merchant review or the CFO: drafted by Cortex AI_COMPLETE from a fact pack, then '
         'fact-checked by a second AI_COMPLETE pass that refuses unsupported or hedged claims.</p>')
    left, right = st.columns([1, 2.2], gap="medium")
    with left.container(key="card_gen"):
        st.markdown("### Write a note")
        scope = st.radio("Scope", list(SCOPES), format_func=lambda k: SCOPES[k], key="scope")
        badge("Cortex AI_COMPLETE · draft + verifier")
        if st.button("Run dispute analysis", type="primary", width="stretch", icon=":material/play_arrow:"):
            with right:
                run_note(scope)
        st.caption("Live runs took 8-11 s in testing and cost two AI_COMPLETE calls.")
    note = st.session_state.get("note")
    with right:
        if not note:
            html('<div class="rb-empty"><b>No note yet.</b><br>Pick a scope and run the analysis. The draft streams in, then the '
                 'verifier stamps it Verified or Needs review.</div>')
        else:
            res, scope = note["res"], note["scope"]
            with st.container(key="card_note"):
                ai_label(res.get("latency_ms"))
                body = res["draft"]
                if note.get("fresh"):
                    ph = st.empty()
                    acc = ""
                    for tok in stream_words(body, 140):
                        acc += tok
                        ph.markdown(cite(acc + " ▍"), unsafe_allow_html=True)
                    ph.markdown(cite(body), unsafe_allow_html=True)
                    note["fresh"] = False
                else:
                    html(cite(body))
                note_view(res, scope, "main")
                with st.expander(f"Sources: fact pack ({len(res['fact_pack'])} rows, cited as F1-F{len(res['fact_pack'])})"):
                    st.dataframe(pd.DataFrame(res["fact_pack"]), hide_index=True, width="stretch")
            with st.container(key="card_break"):
                st.markdown("### Try to break it")
                st.caption("Add a hedged, unsupported sentence to the draft and run only the verifier again.")
                if st.button("Insert a hedge and re-verify", icon=":material/gavel:"):
                    steps = ["Re-reading the fact pack…", "Checking each figure in the edited draft…", "Scanning for hedge words…"]
                    if st.session_state.mode == "Live":
                        box = staged(steps)
                        try:
                            rv = LIVE_OPS_AI["reverify"](live_session(), scope, res["draft"] + HEDGE_LINE)
                        except Exception as e:  # noqa: BLE001
                            live_error(e)
                        box.update(label=f"Verifier done in {rv['latency_ms'] / 1000:.1f} s", state="complete", expanded=False)
                    else:
                        rv = load_sample("reverify", scope)
                        box = staged(steps, random.uniform(4, 6))
                        box.update(label="Verifier done (sample replay)", state="complete", expanded=False)
                    st.session_state["rv"] = {"scope": scope, "rv": rv}
                rv = st.session_state.get("rv")
                if rv and rv["scope"] == scope:
                    ai_label(rv["rv"].get("latency_ms"))
                    html(f'<div class="rb-insight rb-i-lost">Added: <i>{esc(HEDGE_LINE.strip())}</i></div>')
                    note_view(rv["rv"], scope, "rv")
    st.markdown("### Note gallery")
    reports = guarded("reports")
    if not reports:
        html('<div class="rb-empty">No saved notes yet. Each Live run is stored in DISPUTE_REPORTS and shows up here.</div>')
        return
    cols = st.columns(3)
    for i, r in enumerate(reports):
        ok = r["status"] == "verified"
        title = (r.get("report_md") or "").split("\n")[0].lstrip("# ").strip() or r["subject"]
        with cols[i % 3]:
            html(f'<div class="rb-docket {"" if ok else "bad"}">{pill("Verified" if ok else "Needs review", "won" if ok else "lost")}'
                 f'<div class="t">{esc(title[:90])}</div><div class="s">{esc(r["subject"])} · {esc(r["created_at"])} · '
                 f'{r["edits_applied"]} flagged</div></div>')
            if st.button("Open note", key=f"open_{r['run_id']}", width="stretch"):
                report_dialog(r)


@st.dialog("Saved chargeback note", width="large")
def report_dialog(r):
    ok = r["status"] == "verified"
    html(f'<span class="rb-stamp {"rb-stamp-ok" if ok else "rb-stamp-bad"}">{"Verified" if ok else "Needs review"}</span>')
    html(cite(r["report_md"]))
    edits = json.loads(r.get("edits") or "[]")
    if edits:
        html("<b>Verifier flags</b><ul>" + "".join(f"<li>{esc(e)}</li>" for e in edits) + "</ul>")
    if r.get("fact_pack"):
        with st.expander("Sources: fact pack"):
            st.dataframe(pd.DataFrame(json.loads(r["fact_pack"])), hide_index=True, width="stretch")


def render_answer(a, fresh):
    ai_label(a.get("latency_ms"))
    text = a["text"].replace("$", "\\$")  # dollar amounts, not LaTeX
    if fresh:
        st.write_stream(stream_words(text, 80))
    else:
        st.markdown(text)
    for t in a.get("tables", []):
        if t["rows"]:
            st.dataframe(pd.DataFrame(t["rows"], columns=t["columns"] or None), hide_index=True, width="stretch")
    if a.get("sql"):
        with st.expander("Source: SQL generated by Cortex Analyst over DISPUTE_SV"):
            st.code(a["sql"], language="sql")


def page_ask():
    st.title("Ask the desk")
    html('<p class="rb-sub">Plain-English questions answered by a Cortex Agent that writes SQL with Cortex Analyst over the '
         'DISPUTE_SV semantic view. Every figure comes from a query you can inspect.</p>')
    badge("Cortex Agent DISPUTE_AGENT · Cortex Analyst · Semantic View DISPUTE_SV")
    history = st.session_state.setdefault("chat", [])
    cols = st.columns(3)
    asked = None
    for i, q in enumerate(SAMPLE_QUESTIONS):
        if cols[i].button(q, key=f"sq{i}", width="stretch", icon=":material/forum:"):
            asked = q
    typed = st.chat_input("Ask about disputes, reason codes, win rates or complaints"
                          if st.session_state.mode == "Live" else "Sample mode answers the three questions above")
    if typed:
        if st.session_state.mode != "Live" and typed not in SAMPLE_QUESTIONS:
            st.info("Sample mode replays captured answers to the three sample questions. Switch to Live to ask your own.")
        else:
            asked = typed
    for h in history:
        with st.chat_message("user"):
            st.markdown(h["question"])
        with st.chat_message("assistant", avatar=":material/gavel:"):
            render_answer(h, False)
    if asked:
        with st.chat_message("user"):
            st.markdown(asked)
        with st.chat_message("assistant", avatar=":material/gavel:"):
            steps = ["Planning with the Cortex Agent…", "Generating SQL with Cortex Analyst over DISPUTE_SV…",
                     f"Running the query on {WAREHOUSE}…", "Writing the answer from the result set…"]
            if st.session_state.mode == "Live":
                box = staged(steps)
                for s in steps:
                    box.write(f":material/progress_activity: {s}")
                try:
                    a = LIVE_OPS_AI["ask"](live_session(), asked)
                except Exception as e:  # noqa: BLE001
                    box.update(label="Live call failed", state="error")
                    live_error(e)
                box.update(label=f"Answered in {a['latency_ms'] / 1000:.1f} s", state="complete", expanded=False)
            else:
                a = load_sample("ask", SAMPLE_QUESTIONS.index(asked))
                box = staged(steps, random.uniform(5, 8))
                box.update(label="Answered (sample replay)", state="complete", expanded=False)
            render_answer(a, True)
        history.append(a)


LIVE_OPS_AI = {"generate": live_generate, "reverify": live_reverify, "ask": live_ask}
PAGES = {}


def context_bar():
    can_live = live_session() is not None
    has_sample = SAMPLE_DIR.exists()
    if "mode" not in st.session_state:
        st.session_state.mode = "Live" if can_live or not has_sample else "Sample"
    c1, c2 = st.columns([3, 1.1], vertical_alignment="center")
    env = st.session_state.mode
    with c1:
        html('<div class="rb-ctx"><span class="rb-chip"><span class="rb-avatar">DA</span>Dispute analyst · Halvane Payments</span>'
             f'<span class="rb-env rb-env-{env.lower()}">{env}</span><span class="rb-chip">As of {AS_OF}</span>'
             '<span class="rb-chip">Synthetic data</span></div>')
    with c2:
        options = (["Sample"] if has_sample else []) + ["Live"]
        choice = st.segmented_control("Data mode", options, key="mode_pick", default=env, label_visibility="collapsed")
        if choice and choice != env:
            st.session_state.mode = choice
            st.session_state.pop("note", None)
            st.session_state.pop("rv", None)
            st.session_state["chat"] = []
            st.rerun()
    if st.session_state.mode == "Live" and not can_live:
        st.warning("Live mode needs a Snowflake connection. Nothing was switched silently; set these and restart:", icon=":material/link_off:")
        st.code("export SNOWFLAKE_ACCOUNT=<your_account_identifier>\nexport SNOWFLAKE_USER=<YOUR_USER>\n"
                "export SNOWFLAKE_PRIVATE_KEY_PATH=~/.snowflake/keys/<your_key>.p8\n"
                "streamlit run app/streamlit_app.py", language="bash")
        st.caption("Run sql/setup.sql first. Key-pair setup is in the README under \"Run locally in Live mode\". "
                   "Credentials are never collected in the browser.")
        st.stop()


def main():
    st.set_page_config(page_title="Chargeback & Dispute Intelligence", page_icon=":material/gavel:", layout="wide")
    html(CSS)
    logo = Path(__file__).parent / "static" / "logo.svg"
    if logo.exists():
        st.logo(str(logo), size="large")
    PAGES.update({
        "overview": st.Page(page_overview, title="Overview", icon=":material/space_dashboard:", url_path="overview", default=True),
        "reasons": st.Page(page_reasons, title="Reason codes", icon=":material/rule:", url_path="reason-codes"),
        "merchants": st.Page(page_merchants, title="Merchants", icon=":material/storefront:", url_path="merchants"),
        "notes": st.Page(page_notes, title="Chargeback notes", icon=":material/edit_note:", url_path="notes"),
        "ask": st.Page(page_ask, title="Ask the desk", icon=":material/forum:", url_path="ask"),
    })
    nav = st.navigation(list(PAGES.values()), position="top")
    context_bar()
    nav.run()
    html('<p style="color:#4E6064;font-size:.74rem;margin-top:2rem">Halvane Payments is fictional. Synthetic data and '
         'illustrative logic only; not production, regulatory or compliance advice. Owner: Javier Soliz.</p>')


if __name__ == "__main__":
    main()
