"""LATTICE — main page."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.graph_objects as go
st.set_page_config(page_title="LATTICE", layout="wide", initial_sidebar_state="expanded")

from components.sidebar import render_sidebar
from components.theme import src, footer
from ingestion.db import get_connection, get_cursor

render_sidebar()


@st.cache_data(ttl=300)
def home_data():
    conn = get_connection()
    cur = get_cursor(conn)
    s = {}
    cur.execute("SELECT COUNT(*) as c FROM bills"); s["bills"] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM bill_analyses"); s["analyzed"] = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(amount),0) as t FROM contributions"); s["money"] = float(cur.fetchone()["t"])
    cur.execute("SELECT COUNT(DISTINCT legislator_id) as c FROM contributions"); s["legs"] = cur.fetchone()["c"]
    cur.execute("SELECT policy_area, COUNT(*) as c FROM bill_analyses WHERE policy_area IS NOT NULL GROUP BY policy_area ORDER BY c DESC LIMIT 10")
    s["policy"] = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT controversy_score FROM bill_analyses WHERE controversy_score IS NOT NULL")
    s["controversy"] = [r["controversy_score"] for r in cur.fetchall()]
    cur.execute("""SELECT b.bill_number, ba.plain_english, ba.controversy_score, ba.policy_area
        FROM bill_analyses ba JOIN bills b ON b.id = ba.bill_id
        WHERE ba.controversy_score >= 0.7 ORDER BY ba.controversy_score DESC LIMIT 5""")
    s["hot"] = [dict(r) for r in cur.fetchall()]
    conn.close()
    return s


# ── Header ─────────────────────────────────────────────────────────

st.markdown("""
<p style="font-size:0.6rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:0.4rem;">
    Tulane University · Department of Political Science</p>
<h1 style="font-size:2.5rem;line-height:1.08;margin-bottom:0.3rem;">LATTICE</h1>
<p style="font-size:0.82rem;color:#78716c;margin-bottom:1.5rem;">
    Legislative Analysis Through Transparency, Intelligence, and Civic Engagement</p>
""", unsafe_allow_html=True)

# ── Search ─────────────────────────────────────────────────────────

q = st.text_input("search_home", placeholder="Search any bill, legislator, or topic…", label_visibility="collapsed")

if q:
    conn = get_connection()
    cur = get_cursor(conn)
    like = f"%{q}%"
    cur.execute("""SELECT b.bill_number, ba.plain_english, ba.policy_area
        FROM bills b JOIN bill_analyses ba ON ba.bill_id = b.id
        WHERE b.bill_number ILIKE %s OR b.title ILIKE %s OR ba.plain_english ILIKE %s
        LIMIT 8""", (like, like, like))
    bill_results = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT name, party, role, district FROM legislators WHERE name ILIKE %s LIMIT 5", (like,))
    leg_results = [dict(r) for r in cur.fetchall()]
    conn.close()

    if bill_results:
        st.markdown('<h3 style="margin-top:1rem;">Bills</h3>', unsafe_allow_html=True)
        for b in bill_results:
            st.markdown(f"""<div class="lc" style="padding:1rem 1.3rem;">
                <span style="font-family:'Source Serif 4',serif;font-weight:600;color:#1c1917;">{b['bill_number']}</span>
                <span style="font-size:0.63rem;color:#a8a29e;margin-left:0.4rem;">{b.get('policy_area','')}</span>
                <p style="font-size:0.85rem;color:#44403c;line-height:1.6;margin:0.3rem 0 0 0;">{b['plain_english'][:150]}{'…' if len(b['plain_english'])>150 else ''}</p>
            </div>""", unsafe_allow_html=True)

    if leg_results:
        st.markdown('<h3 style="margin-top:1rem;">Legislators</h3>', unsafe_allow_html=True)
        for l in leg_results:
            pc = {"R":"#dc2626","D":"#2563eb"}.get(l["party"],"#78716c")
            st.markdown(f"""<div class="lc" style="padding:0.8rem 1.3rem;display:flex;align-items:center;gap:0.6rem;">
                <span style="color:{pc};font-weight:600;font-size:0.85rem;">{l['party']}</span>
                <span style="font-weight:500;color:#1c1917;">{l['name']}</span>
                <span style="font-size:0.75rem;color:#a8a29e;">{l['role']} · District {l.get('district','?')}</span>
            </div>""", unsafe_allow_html=True)

    if not bill_results and not leg_results:
        st.markdown(f'<p style="color:#a8a29e;font-size:0.85rem;margin-top:0.5rem;">No results for "{q}"</p>', unsafe_allow_html=True)

else:
    # ── Dashboard view ─────────────────────────────────────────────

    s = home_data()

    st.markdown("---")

    # Key figures
    c1, c2, c3, c4 = st.columns(4)
    figures = [
        (c1, f"{s['bills']:,}", "Bills tracked", "LegiScan"),
        (c2, f"{s['analyzed']:,}", "AI-analyzed", "Claude API"),
        (c3, f"${s['money']/1e6:.1f}M", "Contributions mapped", "LA Ethics"),
        (c4, f"{s['legs']}", "Legislators profiled", "LA Ethics"),
    ]
    for col, val, label, source in figures:
        with col:
            st.markdown(f"""<div style="text-align:center;padding:0.6rem 0;">
                <p style="font-family:'Source Serif 4',serif;font-size:1.8rem;font-weight:700;color:#1c1917;margin:0;letter-spacing:-0.02em;">{val}</p>
                <p style="font-size:0.6rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.05em;margin:0.1rem 0 0 0;">{label}</p>
                <p class="src" style="margin-top:0.15rem;">{source}</p>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # Charts
    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        st.markdown('<h3>Bills by policy area</h3>', unsafe_allow_html=True)
        if s["policy"]:
            areas = [d["policy_area"].replace("_"," ").title() for d in s["policy"]]
            counts = [d["c"] for d in s["policy"]]
            fig = go.Figure(go.Bar(x=counts, y=areas, orientation="h",
                marker_color="#4338ca", marker_line_width=0, opacity=0.75))
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#57534e", size=11, family="Inter"),
                xaxis=dict(title="", gridcolor="#ebe9e7", showline=False, zeroline=False),
                yaxis=dict(title="", categoryorder="total ascending", showline=False),
                margin=dict(l=0,r=10,t=5,b=10), height=280)
            fig.add_annotation(x=max(counts)*0.95, y=areas[0],
                text=f"n = {sum(counts)}", showarrow=False,
                font=dict(size=10, color="#a8a29e"))
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(src("Source: AI classification via Claude"), unsafe_allow_html=True)

    with col_b:
        st.markdown('<h3>Controversy score distribution</h3>', unsafe_allow_html=True)
        if s["controversy"]:
            fig = go.Figure(go.Histogram(x=s["controversy"], nbinsx=20,
                marker=dict(color="#4338ca", line=dict(width=0)), opacity=0.7))
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#57534e", size=11, family="Inter"),
                xaxis=dict(title="Score (0 = routine, 1 = highly controversial)", gridcolor="#ebe9e7", range=[0,1]),
                yaxis=dict(title="", gridcolor="#ebe9e7"),
                margin=dict(l=40,r=10,t=5,b=30), height=280, bargap=0.06)
            median_c = sorted(s["controversy"])[len(s["controversy"])//2]
            fig.add_vline(x=median_c, line_dash="dot", line_color="#a8a29e", line_width=1)
            fig.add_annotation(x=median_c+0.03, y=0, text=f"median: {median_c:.2f}",
                showarrow=False, font=dict(size=10, color="#a8a29e"), yanchor="bottom")
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(src("Source: AI heuristic — not a validated measure"), unsafe_allow_html=True)

    # Hot bills
    if s["hot"]:
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown('<h3>Highest controversy bills</h3>', unsafe_allow_html=True)
        for b in s["hot"]:
            st.markdown(f"""<div class="lc" style="padding:1rem 1.3rem;">
                <div style="display:flex;align-items:baseline;gap:0.4rem;margin-bottom:0.3rem;">
                    <span style="font-family:'Source Serif 4',serif;font-weight:600;color:#1c1917;">{b['bill_number']}</span>
                    <span style="font-size:0.63rem;color:#a8a29e;">{(b.get('policy_area') or '').replace('_',' ')}</span>
                    <span style="font-size:0.63rem;color:#dc2626;margin-left:auto;">{b['controversy_score']:.0%} controversy</span>
                </div>
                <p style="font-size:0.85rem;color:#44403c;line-height:1.6;margin:0;">{b['plain_english'][:200]}{'…' if len(b['plain_english'])>200 else ''}</p>
            </div>""", unsafe_allow_html=True)

    st.markdown(footer(), unsafe_allow_html=True)
