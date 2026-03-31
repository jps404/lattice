"""Legislators page."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from components.sidebar import render_sidebar
from components.theme import t, src, footer, page_head
from ingestion.db import get_connection, get_cursor

st.set_page_config(page_title="Legislators — LATTICE", layout="wide")
render_sidebar()


@st.cache_data(ttl=300)
def fetch_legislators(search, pf):
    conn = get_connection()
    cur = get_cursor(conn)
    sql = "SELECT * FROM legislators WHERE active = TRUE"
    params = []
    if search: sql += " AND (name ILIKE %s OR district ILIKE %s)"; params += [f"%{search}%"]*2
    if pf != "All": sql += " AND party = %s"; params.append(pf)
    sql += " ORDER BY last_name, first_name"
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=300)
def fetch_donors(leg_id):
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute("""SELECT donor_name, SUM(amount) as total, contributor_type,
        COUNT(*) as num FROM contributions WHERE legislator_id = %s
        GROUP BY donor_name, contributor_type ORDER BY total DESC LIMIT 20""", (leg_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=300)
def fetch_donor_types(leg_id):
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute("""SELECT contributor_type, SUM(amount) as total, COUNT(*) as num
        FROM contributions WHERE legislator_id = %s
        GROUP BY contributor_type ORDER BY total DESC""", (leg_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=300)
def fetch_bills(leg_id):
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute("""SELECT b.bill_number, ba.plain_english, ba.policy_area, s.sponsor_type
        FROM sponsorships s JOIN bills b ON b.id = s.bill_id
        LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
        WHERE s.legislator_id = %s ORDER BY s.sponsor_type, b.bill_number""", (leg_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


st.markdown(page_head("Legislators", "Campaign donors, sponsored bills, and financial profiles"), unsafe_allow_html=True)

c1, c2 = st.columns([3, 1])
with c1: search = st.text_input("Search", placeholder="Name or district…", label_visibility="collapsed")
with c2: pf = st.selectbox("Party", ["All", "R", "D", "I"])

legs = fetch_legislators(search, pf)
st.markdown(f'<p style="color:#a8a29e;font-size:0.75rem;margin-bottom:0.6rem;">{len(legs)} legislators</p>', unsafe_allow_html=True)

for leg in legs:
    party = leg.get("party", "?")
    pc = {"R":"#dc2626","D":"#2563eb","I":"#7c3aed"}.get(party, "#78716c")

    with st.expander(f'{leg["name"]}  ·  {party}  ·  {leg.get("role","")}  ·  District {leg.get("district","?")}'):
        st.markdown(f"""<div style="display:flex;align-items:center;gap:0.65rem;margin-bottom:1rem;">
            <div style="width:38px;height:38px;border-radius:50%;background:{pc}10;
                display:flex;align-items:center;justify-content:center;
                font-weight:600;color:{pc};font-size:0.85rem;border:1.5px solid {pc}30;">{party}</div>
            <div>
                <p style="font-family:'Source Serif 4',serif;font-size:1.05rem;font-weight:600;color:#1c1917;margin:0;">{leg['name']}</p>
                <p style="font-size:0.75rem;color:#78716c;margin:0;">{leg.get('role','')} · District {leg.get('district','?')}</p>
            </div>
        </div>""", unsafe_allow_html=True)

        if leg.get("ballotpedia_url"):
            st.caption(f"[Ballotpedia →]({leg['ballotpedia_url']})")

        # Donors
        donors = fetch_donors(leg["id"])
        donor_types = fetch_donor_types(leg["id"])

        if donors:
            total_raised = sum(d["total"] for d in donors)
            st.markdown(f'<p style="font-size:0.82rem;color:#57534e;">Total raised: <span style="font-weight:600;color:#1c1917;">${total_raised:,.0f}</span> {src("LA Ethics 2024–27")}</p>', unsafe_allow_html=True)

            if donor_types:
                df = pd.DataFrame(donor_types)
                df["total"] = df["total"].astype(float)
                fig = go.Figure(go.Bar(x=df["total"], y=df["contributor_type"], orientation="h",
                    marker_color="#4338ca", marker_line_width=0, opacity=0.85))
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#57534e", size=11, family="Inter"),
                    xaxis=dict(title="", gridcolor="#e7e5e4", showline=False),
                    yaxis=dict(title="", categoryorder="total ascending", showline=False),
                    margin=dict(l=0,r=0,t=5,b=5), height=180)
                st.plotly_chart(fig, use_container_width=True)

            st.caption("Top donors")
            for d in donors[:10]:
                st.markdown(f"""<div style="padding:0.3rem 0;border-bottom:1px solid #f0eeec;display:flex;justify-content:space-between;">
                    <span style="font-size:0.8rem;color:#44403c;">{d['donor_name'][:50]}</span>
                    <span style="font-size:0.8rem;font-weight:500;color:#1c1917;">${float(d['total']):,.0f}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#a8a29e;font-size:0.82rem;">No contribution data yet</p>', unsafe_allow_html=True)

        # Bills
        bills = fetch_bills(leg["id"])
        if bills:
            st.caption(f"Sponsored bills ({len(bills)})")
            for b in bills[:15]:
                badge = t("PRIMARY","a") if b["sponsor_type"]=="Primary" else t("CO-SPONSOR","m")
                pa = " "+t(b["policy_area"],"b") if b.get("policy_area") else ""
                txt = b.get("plain_english") or "Analysis pending"
                if len(txt)>95: txt = txt[:95]+"…"
                st.markdown(f"""<div style="padding:0.35rem 0;border-bottom:1px solid #f0eeec;">
                    <div style="display:flex;gap:0.35rem;align-items:center;margin-bottom:0.1rem;">
                        <span style="font-weight:500;font-size:0.8rem;color:#1c1917;">{b['bill_number']}</span> {badge}{pa}
                    </div>
                    <p style="font-size:0.78rem;color:#57534e;margin:0;">{txt}</p>
                </div>""", unsafe_allow_html=True)
