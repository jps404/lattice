"""{L.A}TTICE — main page."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
st.set_page_config(page_title="{L.A}TTICE", layout="wide", initial_sidebar_state="expanded")

from components.sidebar import render_sidebar
from components.theme import LOGO_HTML, src, footer
from ingestion.db import get_connection, get_cursor

render_sidebar()


@st.cache_data(ttl=300)
def home_data():
    conn = get_connection(); cur = get_cursor(conn); s = {}
    cur.execute("SELECT COUNT(*) as c FROM bills"); s["bills"] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM bill_analyses"); s["analyzed"] = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(amount),0) as t FROM contributions"); s["money"] = float(cur.fetchone()["t"])
    cur.execute("SELECT COUNT(DISTINCT legislator_id) as c FROM contributions"); s["legs"] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM conflict_flags"); s["flags"] = cur.fetchone()["c"]
    cur.execute("SELECT policy_area, COUNT(*) as c FROM bill_analyses WHERE policy_area IS NOT NULL GROUP BY policy_area ORDER BY c DESC LIMIT 12")
    s["policy"] = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT controversy_score FROM bill_analyses WHERE controversy_score IS NOT NULL")
    s["controversy"] = [r["controversy_score"] for r in cur.fetchall()]
    cur.execute("""SELECT b.bill_number, ba.plain_english, ba.controversy_score, ba.policy_area
        FROM bill_analyses ba JOIN bills b ON b.id = ba.bill_id
        WHERE ba.controversy_score >= 0.7 ORDER BY ba.controversy_score DESC LIMIT 5""")
    s["hot"] = [dict(r) for r in cur.fetchall()]
    # Top money legislators
    cur.execute("""SELECT l.name, l.party, SUM(c.amount) as total
        FROM contributions c JOIN legislators l ON l.id = c.legislator_id
        GROUP BY l.name, l.party ORDER BY total DESC LIMIT 8""")
    s["top_money"] = [dict(r) for r in cur.fetchall()]
    conn.close()
    return s


st.markdown(f"""
<div style="max-width:660px;padding:2rem 0 0.75rem 0;">
    <p style="font-size:0.6rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:0.5rem;">
        Tulane University · Department of Political Science</p>
    <h1 style="font-size:2.8rem;line-height:1.05;margin-bottom:0.5rem;">
        <span style="color:#4338ca;">{{L.A}}</span>TTICE
    </h1>
    <p style="font-size:0.88rem;color:#78716c;line-height:1.7;margin-top:0.5rem;">
        Legislative Analysis Through Transparency, Intelligence, and Civic Engagement.
        A computational platform mapping money, legislation, and political outcomes
        in the Louisiana state legislature.
    </p>
</div>
""", unsafe_allow_html=True)

# Search
q = st.text_input("s", placeholder="Search any bill, legislator, or topic…", label_visibility="collapsed")

if q:
    conn = get_connection(); cur = get_cursor(conn); like = f"%{q}%"
    cur.execute("""SELECT b.bill_number, ba.plain_english, ba.policy_area
        FROM bills b JOIN bill_analyses ba ON ba.bill_id = b.id
        WHERE b.bill_number ILIKE %s OR b.title ILIKE %s OR ba.plain_english ILIKE %s LIMIT 8""", (like,like,like))
    bills = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT name, party, role, district FROM legislators WHERE name ILIKE %s LIMIT 5", (like,))
    legs = [dict(r) for r in cur.fetchall()]
    conn.close()

    if bills:
        for b in bills:
            st.markdown(f"""<div class="lc" style="padding:1rem 1.3rem;">
                <span style="font-family:'Source Serif 4',serif;font-weight:600;color:#1c1917;">{b['bill_number']}</span>
                <span style="font-size:0.63rem;color:#a8a29e;margin-left:0.3rem;">{b.get('policy_area','')}</span>
                <p style="font-size:0.85rem;color:#44403c;line-height:1.6;margin:0.25rem 0 0 0;">{b['plain_english'][:160]}{'…' if len(b['plain_english'])>160 else ''}</p>
            </div>""", unsafe_allow_html=True)
    if legs:
        for l in legs:
            pc = {"R":"#dc2626","D":"#2563eb"}.get(l["party"],"#78716c")
            st.markdown(f"""<div class="lc" style="padding:0.75rem 1.3rem;display:flex;align-items:center;gap:0.5rem;">
                <span style="color:{pc};font-weight:600;font-size:0.85rem;">{l['party']}</span>
                <span style="font-weight:500;color:#1c1917;">{l['name']}</span>
                <span style="font-size:0.75rem;color:#a8a29e;">{l['role']} · District {l.get('district','?')}</span>
            </div>""", unsafe_allow_html=True)
    if not bills and not legs:
        st.markdown(f'<p style="color:#a8a29e;font-size:0.85rem;">No results for "{q}"</p>', unsafe_allow_html=True)

else:
    s = home_data()
    st.markdown("---")

    # Key figures
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, label, source in [
        (c1, f"{s['bills']:,}", "Bills", "LegiScan"),
        (c2, f"{s['analyzed']:,}", "AI-analyzed", "Claude"),
        (c3, f"${s['money']/1e6:.1f}M", "Contributions", "LA Ethics"),
        (c4, f"{s['legs']}", "Legislators", ""),
        (c5, f"{s['flags']}", "Conflict flags", ""),
    ]:
        with col:
            st.markdown(f"""<div style="text-align:center;padding:0.5rem 0;">
                <p style="font-family:'Source Serif 4',serif;font-size:1.6rem;font-weight:700;color:#1c1917;margin:0;">{val}</p>
                <p style="font-size:0.58rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.05em;margin:0;">{label}</p>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # Charts row
    col_a, col_b, col_c = st.columns([2, 2, 1.5], gap="large")

    with col_a:
        st.markdown('<h3>Bills by policy area</h3>', unsafe_allow_html=True)
        if s["policy"]:
            areas = [d["policy_area"].replace("_"," ").title() for d in s["policy"]]
            counts = [d["c"] for d in s["policy"]]
            fig = go.Figure(go.Bar(x=counts, y=areas, orientation="h",
                marker_color="#4338ca", opacity=0.75))
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#57534e", size=10, family="Inter"),
                xaxis=dict(title="", gridcolor="#ebe9e7", showline=False, zeroline=False),
                yaxis=dict(title="", categoryorder="total ascending", showline=False),
                margin=dict(l=0,r=5,t=5,b=5), height=300)
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown('<h3>Controversy distribution</h3>', unsafe_allow_html=True)
        if s["controversy"]:
            fig = go.Figure(go.Histogram(x=s["controversy"], nbinsx=20,
                marker=dict(color="#4338ca"), opacity=0.7))
            med = sorted(s["controversy"])[len(s["controversy"])//2]
            fig.add_vline(x=med, line_dash="dot", line_color="#a8a29e", line_width=1)
            fig.add_annotation(x=med+0.04, y=0, text=f"median {med:.2f}",
                showarrow=False, font=dict(size=9, color="#a8a29e"), yanchor="bottom")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#57534e", size=10, family="Inter"),
                xaxis=dict(title="0 = routine → 1 = controversial", gridcolor="#ebe9e7", range=[0,1]),
                yaxis=dict(title="", gridcolor="#ebe9e7"),
                margin=dict(l=30,r=5,t=5,b=25), height=300, bargap=0.06)
            st.plotly_chart(fig, use_container_width=True)

    with col_c:
        st.markdown('<h3>Top fundraisers</h3>', unsafe_allow_html=True)
        if s["top_money"]:
            for leg in s["top_money"]:
                pc = {"R":"#dc2626","D":"#2563eb"}.get(leg["party"],"#78716c")
                st.markdown(f"""<div style="padding:0.3rem 0;border-bottom:1px solid #f0eeec;display:flex;justify-content:space-between;">
                    <span style="font-size:0.78rem;color:#44403c;"><span style="color:{pc};font-weight:500;">{leg['party']}</span> {leg['name'][:20]}</span>
                    <span style="font-size:0.78rem;color:#1c1917;font-weight:500;">${float(leg['total'])/1000:.0f}K</span>
                </div>""", unsafe_allow_html=True)
            st.markdown(f'<p class="src" style="margin-top:0.4rem;">LA Ethics 2024–27</p>', unsafe_allow_html=True)

    # Hot bills
    if s["hot"]:
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        st.markdown('<h3>Highest controversy bills</h3>', unsafe_allow_html=True)
        for b in s["hot"]:
            st.markdown(f"""<div class="lc" style="padding:1rem 1.3rem;">
                <div style="display:flex;align-items:baseline;gap:0.4rem;margin-bottom:0.25rem;">
                    <span style="font-family:'Source Serif 4',serif;font-weight:600;color:#1c1917;">{b['bill_number']}</span>
                    <span style="font-size:0.63rem;color:#a8a29e;">{(b.get('policy_area') or '').replace('_',' ')}</span>
                    <span style="font-size:0.63rem;color:#dc2626;margin-left:auto;">{b['controversy_score']:.0%}</span>
                </div>
                <p style="font-size:0.85rem;color:#44403c;line-height:1.6;margin:0;">{b['plain_english'][:200]}{'…' if len(b['plain_english'])>200 else ''}</p>
            </div>""", unsafe_allow_html=True)

    st.markdown(footer(), unsafe_allow_html=True)
