"""Bills page."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import streamlit as st
from components.sidebar import render_sidebar
from components.theme import t, src, footer, page_head
from ingestion.db import get_connection, get_cursor

st.set_page_config(page_title="Bills — LATTICE", layout="wide")
render_sidebar()


@st.cache_data(ttl=300)
def fetch_analyzed(q, sf, pf, sort):
    conn = get_connection(); cur = get_cursor(conn)
    sql = """SELECT b.bill_number, b.title, b.current_status, b.url,
             ba.plain_english, ba.key_changes, ba.who_benefits, ba.who_is_harmed,
             ba.policy_area, ba.controversy_score, p.pass_probability
             FROM bills b JOIN bill_analyses ba ON ba.bill_id = b.id
             LEFT JOIN predictions p ON p.bill_id = b.id WHERE 1=1"""
    p = []
    if q: sql += " AND (b.bill_number ILIKE %s OR b.title ILIKE %s OR ba.plain_english ILIKE %s)"; p += [f"%{q}%"]*3
    if sf != "All": sql += " AND b.current_status = %s"; p.append(sf)
    if pf != "All": sql += " AND ba.policy_area = %s"; p.append(pf)
    order = {"Controversy":"ba.controversy_score DESC NULLS LAST","Bill Number":"b.bill_number","Newest":"b.created_at DESC"}
    sql += f" ORDER BY {order[sort]} LIMIT 50"
    cur.execute(sql, p); rows = [dict(r) for r in cur.fetchall()]; conn.close()
    return rows


@st.cache_data(ttl=300)
def fetch_all(q, sf):
    conn = get_connection(); cur = get_cursor(conn)
    sql = "SELECT b.bill_number, b.title, ba.plain_english FROM bills b LEFT JOIN bill_analyses ba ON ba.bill_id = b.id WHERE 1=1"
    p = []
    if q: sql += " AND (b.bill_number ILIKE %s OR b.title ILIKE %s)"; p += [f"%{q}%"]*2
    if sf != "All": sql += " AND b.current_status = %s"; p.append(sf)
    sql += " ORDER BY b.bill_number LIMIT 200"
    cur.execute(sql, p); rows = [dict(r) for r in cur.fetchall()]; conn.close()
    return rows


st.markdown(page_head("Bills", "What each bill actually does, in plain English"), unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
with c1: q = st.text_input("s", placeholder="Search bills…", label_visibility="collapsed")
with c2: sf = st.selectbox("Status", ["All","Introduced","Engrossed","Enrolled","Passed","Failed","Vetoed"])
with c3: pf = st.selectbox("Policy", ["All","healthcare","education","energy","environment",
    "criminal_justice","taxation","housing","labor","technology","transportation","agriculture","other"])
with c4: sort = st.selectbox("Sort", ["Controversy","Bill Number","Newest"])

tab1, tab2 = st.tabs(["Analyzed", "All Bills"])

with tab1:
    bills = fetch_analyzed(q, sf, pf, sort)
    if not bills:
        st.markdown('<div class="lc" style="text-align:center;padding:2.5rem;"><p style="color:#a8a29e;">No bills match your filters</p></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p style="color:#b5b0ab;font-size:0.7rem;margin-bottom:0.5rem;">{len(bills)} results · {src("LegiScan + Claude AI")}</p>', unsafe_allow_html=True)

        for b in bills:
            # Summary-first layout
            cs = b.get("controversy_score") or 0
            pr = b.get("pass_probability")
            policy = (b.get("policy_area") or "").replace("_"," ")

            # Right-side metadata
            meta_parts = []
            if policy: meta_parts.append(f'<span style="font-size:0.63rem;color:#a8a29e;">{policy}</span>')
            if cs > 0.5:
                cc = "#dc2626" if cs >= 0.7 else "#d97706"
                meta_parts.append(f'<span style="font-size:0.63rem;color:{cc};">{cs:.0%}</span>')
            if pr is not None:
                pc = "#059669" if pr >= 0.65 else "#dc2626" if pr <= 0.35 else "#d97706"
                meta_parts.append(f'<span style="font-size:0.63rem;color:{pc};">{pr:.0%} pass</span>')

            meta = ' · '.join(meta_parts) if meta_parts else ''

            st.markdown(f"""<div class="lc">
                <p style="font-size:0.88rem;color:#292524;line-height:1.7;margin:0 0 0.5rem 0;">{b.get('plain_english','')}</p>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:baseline;gap:0.4rem;">
                        <span style="font-weight:600;font-size:0.8rem;color:#57534e;">{b['bill_number']}</span>
                        <span style="font-size:0.7rem;color:#b5b0ab;">{b['title'][:60]}{'…' if len(b['title'])>60 else ''}</span>
                    </div>
                    <div>{meta}</div>
                </div>
            </div>""", unsafe_allow_html=True)

            with st.expander(f"Details — {b['bill_number']}"):
                c1, c2 = st.columns(2)
                changes = b.get("key_changes")
                if changes:
                    if isinstance(changes, str):
                        try: changes = json.loads(changes)
                        except: changes = [changes]
                    if isinstance(changes, list) and changes:
                        with c1:
                            st.caption("Key changes")
                            for ch in changes: st.markdown(f"- {ch}")
                with c2:
                    if b.get("who_benefits"):
                        st.caption("Who benefits"); st.write(b["who_benefits"])
                    if b.get("who_is_harmed"):
                        st.caption("Who is harmed"); st.write(b["who_is_harmed"])
                if b.get("url"):
                    st.markdown(f"[Read original text →]({b['url']})")

    # CSV export
    if bills:
        import pandas as pd
        df = pd.DataFrame([{
            "bill_number": b["bill_number"], "title": b["title"], "status": b["current_status"],
            "plain_english": b.get("plain_english",""), "policy_area": b.get("policy_area",""),
            "controversy": b.get("controversy_score",0), "pass_probability": b.get("pass_probability"),
        } for b in bills])
        st.download_button("Export CSV", df.to_csv(index=False), "lattice_bills.csv", "text/csv")

with tab2:
    all_b = fetch_all(q, sf)
    st.markdown(f'<p style="color:#b5b0ab;font-size:0.7rem;margin-bottom:0.4rem;">{len(all_b)} bills</p>', unsafe_allow_html=True)
    for b in all_b:
        done = b.get("plain_english") is not None
        dot = "#059669" if done else "#d6d3d1"
        txt = b.get("plain_english") or b.get("title","")
        if len(txt)>110: txt = txt[:110]+"…"
        st.markdown(f"""<div style="padding:0.4rem 0;border-bottom:1px solid #f0eeec;display:flex;align-items:baseline;gap:0.5rem;">
            <span style="color:{dot};font-size:0.45rem;">●</span>
            <span style="font-weight:500;font-size:0.78rem;color:#57534e;min-width:55px;">{b['bill_number']}</span>
            <span style="font-size:0.78rem;color:#78716c;">{txt}</span>
        </div>""", unsafe_allow_html=True)

st.markdown(footer(), unsafe_allow_html=True)
