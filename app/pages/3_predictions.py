"""Predictions page."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from components.sidebar import render_sidebar
from components.theme import t, src, footer, page_head
from ingestion.db import get_connection, get_cursor

st.set_page_config(page_title="Predictions — LATTICE", layout="wide")
render_sidebar()


@st.cache_data(ttl=300)
def pred_data():
    conn = get_connection(); cur = get_cursor(conn)
    cur.execute("SELECT COUNT(*) as c FROM predictions"); total = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM predictions WHERE actual_outcome IS NOT NULL"); resolved = cur.fetchone()["c"]
    cur.execute("SELECT pass_probability FROM predictions"); probs = [r["pass_probability"] for r in cur.fetchall()]
    conn.close()
    return total, resolved, probs


@st.cache_data(ttl=300)
def pred_list(sort):
    conn = get_connection(); cur = get_cursor(conn)
    order = {"Most likely":"p.pass_probability DESC","Least likely":"p.pass_probability ASC","Bill Number":"b.bill_number"}
    cur.execute(f"""SELECT b.bill_number, b.title, ba.policy_area, ba.plain_english, p.pass_probability
        FROM predictions p JOIN bills b ON b.id = p.bill_id
        LEFT JOIN bill_analyses ba ON ba.bill_id = b.id ORDER BY {order[sort]} LIMIT 60""")
    rows = [dict(r) for r in cur.fetchall()]; conn.close()
    return rows


st.markdown(page_head("Predictions", "Passage probability estimates from logistic regression on historical outcomes"), unsafe_allow_html=True)

total, resolved, probs = pred_data()

c1, c2, c3 = st.columns(3)
for col, val, label in [(c1, f"{total:,}", "Predictions"), (c2, f"{resolved}", "Resolved"), (c3, f"{sum(p>=0.5 for p in probs)}", "Predicted to pass")]:
    with col:
        st.markdown(f"""<div style="text-align:center;padding:0.5rem 0;">
            <p style="font-family:'Source Serif 4',serif;font-size:1.6rem;font-weight:700;color:#1c1917;margin:0;">{val}</p>
            <p style="font-size:0.58rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.06em;margin:0;">{label}</p>
        </div>""", unsafe_allow_html=True)

if probs:
    fig = go.Figure(go.Histogram(x=probs, nbinsx=20,
        marker=dict(color="#4338ca", line=dict(width=0)), opacity=0.7))
    median_p = sorted(probs)[len(probs)//2]
    fig.add_vline(x=median_p, line_dash="dot", line_color="#a8a29e", line_width=1)
    fig.add_annotation(x=median_p+0.03, y=0, text=f"median: {median_p:.2f}",
        showarrow=False, font=dict(size=10, color="#a8a29e"), yanchor="bottom")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#78716c", size=11, family="Inter"),
        xaxis=dict(title="Predicted probability", gridcolor="#ebe9e7", range=[0,1]),
        yaxis=dict(title="", gridcolor="#ebe9e7"),
        margin=dict(l=40,r=10,t=10,b=30), height=180, bargap=0.06)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(f'<p class="src">Logistic regression · 5-fold CV · Brier score · n = {total}</p>', unsafe_allow_html=True)

st.markdown("---")
sort = st.selectbox("Sort", ["Most likely","Least likely","Bill Number"])
preds = pred_list(sort)

for pr in preds:
    prob = pr["pass_probability"]
    pc = "#059669" if prob>=0.65 else "#dc2626" if prob<=0.35 else "#d97706"
    policy = (pr.get("policy_area") or "").replace("_"," ")
    txt = (pr.get("plain_english") or pr["title"])
    if len(txt)>130: txt = txt[:130]+"…"

    st.markdown(f"""<div class="lc" style="padding:1rem 1.3rem;">
        <p style="font-size:0.85rem;color:#44403c;line-height:1.6;margin:0 0 0.4rem 0;">{txt}</p>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
            <div style="display:flex;align-items:baseline;gap:0.4rem;">
                <span style="font-weight:500;font-size:0.78rem;color:#57534e;">{pr['bill_number']}</span>
                <span style="font-size:0.63rem;color:#a8a29e;">{policy}</span>
            </div>
            <span style="font-weight:600;font-size:0.82rem;color:{pc};">{prob:.0%}</span>
        </div>
        <div style="height:2px;background:#ebe9e7;border-radius:1px;overflow:hidden;">
            <div style="width:{prob*100}%;height:100%;background:{pc};border-radius:1px;"></div>
        </div>
    </div>""", unsafe_allow_html=True)

st.markdown(footer(), unsafe_allow_html=True)
