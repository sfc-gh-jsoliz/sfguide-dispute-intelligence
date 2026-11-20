import json
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Dispute Intelligence", layout="wide")

SCHEMA = "SNOWPACK_DISPUTE_INTEL.CORE"
MODEL = "claude-sonnet-4-5"
session = get_active_session()
_rerun = getattr(st, "rerun", getattr(st, "experimental_rerun", lambda: None))
BADGE = {"verified": "✅ Verified", "needs_review": "⚠️ Needs review"}


def sql_df(q, p=None):
    df = session.sql(q, params=p or []).to_pandas()
    df.columns = [c.lower() for c in df.columns]
    return df


def data_mode():
    try:
        r = session.sql(f"SELECT mode, note FROM {SCHEMA}.DISPUTE_DATA_SOURCE_INFO").collect()[0]
        return r[0], r[1]
    except Exception:
        return "unknown", ""


def load_reports():
    return sql_df(f"SELECT run_id, subject, status, edits_applied, residual_hedges, report_md, created_at FROM {SCHEMA}.DISPUTE_REPORTS ORDER BY created_at DESC")


def fact_pack():
    return session.sql(f"""
        WITH w AS (SELECT MIN(month_end) a, MAX(month_end) z FROM {SCHEMA}.DISPUTE_BENCHMARK),
        agg AS (
          SELECT s.reason_category, s.month_end,
                 SUM(s.dispute_count) AS dispute_count,
                 SUM(s.total_dispute_amount) AS dispute_usd,
                 SUM(s.won_count) AS won, SUM(s.resolved_count) AS resolved,
                 SUM(s.friendly_fraud_count) AS friendly_fraud,
                 MAX(s.cfpb_complaint_count) AS cfpb_complaints
          FROM {SCHEMA}.DISPUTE_BENCHMARK s JOIN w ON s.month_end IN (w.a, w.z)
          GROUP BY 1, 2
        )
        SELECT ARRAY_AGG(OBJECT_CONSTRUCT(
          'reason_category', reason_category, 'month', month_end::string,
          'dispute_count', dispute_count, 'dispute_usd', dispute_usd,
          'win_rate', ROUND(won/NULLIF(resolved,0), 3),
          'friendly_fraud_rate', ROUND(friendly_fraud/NULLIF(dispute_count,0), 3),
          'cfpb_complaints', cfpb_complaints))
        FROM agg
    """).collect()[0][0]


def draft_note(fp):
    rules = (
        "You are a payments dispute-ops analyst. Write a concise chargeback note using ONLY the FACTS JSON.\n"
        "DATA RULES: use only numbers in FACTS, copy exactly; win_rate and friendly_fraud_rate are fractions (0-1), express as %; "
        "dollars are USD, express $M/$K; cfpb_complaints is a monthly external benchmark (do not sum across reason categories); "
        "compare the latest month vs the earliest per reason category; no estimates, no hedging, no outside benchmarks; missing = n/d.\n"
        "OUTPUT markdown starting with '# ', a one-line takeaway (which reason categories drove disputes), a table "
        "(reason category | disputes start->now | disputed $ | win rate | friendly-fraud rate), 3 bullets, ending with '## Data Coverage'."
    )
    return session.sql("SELECT AI_COMPLETE(?, ?)", params=[MODEL, rules + f"\n\nFACTS: {fp}"]).collect()[0][0]


def verify(fp, draft):
    vp = (
        "You are a fact-checker. Compare the DRAFT against the FACTS JSON (only allowed source). Return ONLY a JSON object with keys "
        "status ('verified' if every number/claim is supported and no hedge words like likely/approximately/around/could, else 'needs_review'), "
        "residual_hedges (int), edits (array of strings).\n\n" + f"FACTS: {fp}\n\nDRAFT:\n{draft}"
    )
    raw = session.sql("SELECT AI_COMPLETE(?, ?)", params=[MODEL, vp]).collect()[0][0]
    s, e = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[s:e + 1])
    except Exception:
        return {"status": "needs_review", "residual_hedges": None, "edits": ["unparseable verifier output"]}


st.title("Dispute Intelligence")
st.caption("A payments processor's card disputes by reason code / network / merchant category vs a consumer-complaint benchmark.")
_mode, _note = data_mode()
if _mode == "synthetic":
    st.warning("Sample mode — synthetic complaint benchmark. " + _note)
elif _mode == "marketplace":
    st.info("Live benchmark — " + _note)

if "view" not in st.session_state:
    st.session_state["view"] = "gallery"

with st.sidebar:
    st.subheader("Generate a note")
    st.caption("Benchmarks the dispute book by reason category and writes a verified chargeback note.")
    if st.button("Run dispute analysis", type="primary", use_container_width=True):
        with st.spinner("Fact pack → grounded draft → verify (~20-40s)..."):
            fp = fact_pack()
            draft = draft_note(fp)
            v = verify(fp, draft)
            status = "verified" if v.get("status") == "verified" else "needs_review"
            session.sql(
                f"INSERT INTO {SCHEMA}.DISPUTE_REPORTS (subject, draft_md, report_md, status, edits_applied, residual_hedges) SELECT ?, ?, ?, ?, ?, ?",
                params=["Dispute & chargeback review", draft, draft, status, len(v.get("edits", [])), v.get("residual_hedges")],
            ).collect()
        st.success(f"Done — {BADGE[status]}")
        st.session_state["view"] = "gallery"
        _rerun()

if st.session_state["view"].startswith("report:"):
    run_id = st.session_state["view"].split(":", 1)[1]
    rpt = load_reports()
    row = rpt[rpt["run_id"] == run_id]
    if st.button("← Back to gallery"):
        st.session_state["view"] = "gallery"
        _rerun()
    if not row.empty:
        r = row.iloc[0]
        st.markdown(f"**{BADGE.get(r['status'], r['status'])}**  &nbsp; residual hedges: {r['residual_hedges']}  |  flagged: {r['edits_applied']}")
        st.divider()
        st.markdown(r["report_md"])
else:
    reports = load_reports()
    if reports.empty:
        st.info("No notes yet. Use the sidebar to generate one.")
    else:
        cols = st.columns(3)
        for i, (_, r) in enumerate(reports.iterrows()):
            with cols[i % 3]:
                c = st.container()
                c.markdown(f"**{BADGE.get(r['status'], r['status'])}**")
                c.markdown(f"**{r['subject']}**")
                c.caption(f"{str(r['created_at'])[:16]} · {r['edits_applied']} flagged")
                if c.button("Open report", key=f"open_{r['run_id']}", use_container_width=True):
                    st.session_state["view"] = f"report:{r['run_id']}"
                    _rerun()
                c.markdown("---")
