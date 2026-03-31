"""Sidebar."""

import streamlit as st
from components.theme import inject_css, LOGO_SM
from ingestion.db import get_connection, get_cursor


@st.cache_data(ttl=120)
def _stats():
    try:
        conn = get_connection(); cur = get_cursor(conn)
        s = {}
        for tbl, key in [("bills","bills"),("bill_analyses","analyzed"),("predictions","preds"),("conflict_flags","flags")]:
            cur.execute(f"SELECT COUNT(*) as c FROM {tbl}"); s[key] = cur.fetchone()["c"]
        cur.execute("SELECT COALESCE(SUM(amount),0) as t FROM contributions"); s["money"] = float(cur.fetchone()["t"])
        conn.close(); return s
    except:
        return {"bills":0,"analyzed":0,"preds":0,"flags":0,"money":0}


def render_sidebar():
    inject_css()
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:0.5rem 0 0.75rem 0;">
            {LOGO_SM}
            <p style="font-size:0.55rem;color:#a8a29e;text-transform:uppercase;
                letter-spacing:0.12em;margin:0.15rem 0 0 0;">Tulane · Political Science</p>
        </div><hr style="margin:0 0 0.75rem 0;">
        """, unsafe_allow_html=True)

        s = _stats()
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-bottom:0.75rem;">
            <div style="text-align:center;padding:0.5rem 0;">
                <p style="font-family:'Source Serif 4',serif;font-size:1.4rem;font-weight:700;color:#1c1917;margin:0;">{s['analyzed']:,}</p>
                <p style="font-size:0.55rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.06em;margin:0;">Analyzed</p></div>
            <div style="text-align:center;padding:0.5rem 0;">
                <p style="font-family:'Source Serif 4',serif;font-size:1.4rem;font-weight:700;color:#1c1917;margin:0;">${s['money']/1e6:.1f}M</p>
                <p style="font-size:0.55rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.06em;margin:0;">Mapped</p></div>
            <div style="text-align:center;padding:0.5rem 0;">
                <p style="font-family:'Source Serif 4',serif;font-size:1.4rem;font-weight:700;color:#1c1917;margin:0;">{s['preds']:,}</p>
                <p style="font-size:0.55rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.06em;margin:0;">Predictions</p></div>
            <div style="text-align:center;padding:0.5rem 0;">
                <p style="font-family:'Source Serif 4',serif;font-size:1.4rem;font-weight:700;color:#1c1917;margin:0;">{s['flags']:,}</p>
                <p style="font-size:0.55rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.06em;margin:0;">Flags</p></div>
        </div>
        <div style="padding-top:0.5rem;border-top:1px solid #ebe9e7;">
            <p style="font-size:0.55rem;color:#b5b0ab;line-height:1.7;">
                Data: LegiScan, LA Ethics<br>Louisiana 2024–2026 · v0.1</p></div>
        """, unsafe_allow_html=True)
