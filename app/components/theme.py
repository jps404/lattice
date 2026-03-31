"""LATTICE design system."""

import streamlit as st

ACCENT = "#4338ca"
LOGO_HTML = '<span style="font-family:\'Source Serif 4\',Georgia,serif;font-weight:700;letter-spacing:-0.03em;"><span style="color:#4338ca;">{L.A}</span>TTICE</span>'
LOGO_SM = '<span style="font-family:\'Source Serif 4\',serif;font-weight:700;font-size:1.35rem;letter-spacing:-0.03em;"><span style="color:#4338ca;">{L.A}</span>TTICE</span>'


def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600;700&family=Inter:wght@300;400;450;500;600&display=swap');

    .stApp { background: #fafaf9; color: #1c1917; }
    section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid #ebe9e7; }

    h1 { font-family: 'Source Serif 4', Georgia, serif !important; font-weight: 700 !important;
         letter-spacing: -0.025em !important; color: #1c1917 !important;
         -webkit-text-fill-color: #1c1917 !important; background: none !important; }
    h2 { font-family: 'Source Serif 4', Georgia, serif !important; font-weight: 600 !important; color: #1c1917 !important; }
    h3 { font-family: 'Inter', sans-serif !important; font-weight: 500 !important; font-size: 0.68rem !important;
         text-transform: uppercase !important; letter-spacing: 0.09em !important; color: #a8a29e !important; }
    p, li, span, div { font-family: 'Inter', -apple-system, sans-serif; }

    .lc { background: #fff; border: 1px solid #ebe9e7; border-radius: 10px;
          padding: 1.3rem 1.5rem; margin-bottom: 0.75rem; transition: box-shadow 0.15s ease; }
    .lc:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.04); border-color: #ddd; }

    .lt { display: inline-flex; align-items: center; padding: 0.12rem 0.45rem;
          border-radius: 3px; font-size: 0.63rem; font-weight: 500; letter-spacing: 0.01em; }
    .lt-a  { background: #eef2ff; color: #4338ca; }
    .lt-g  { background: #ecfdf5; color: #059669; }
    .lt-r  { background: #fef2f2; color: #dc2626; }
    .lt-o  { background: #fffbeb; color: #d97706; }
    .lt-b  { background: #eff6ff; color: #2563eb; }
    .lt-m  { background: #f5f5f4; color: #78716c; }

    .stExpander { background: #fff; border: 1px solid #ebe9e7 !important; border-radius: 10px !important; margin-bottom: 0.5rem; }
    .stExpander details summary { font-weight: 450 !important; font-size: 0.84rem; color: #57534e; }

    div[data-testid="stMetric"] { background: #fff; border: 1px solid #ebe9e7; border-radius: 10px; padding: 0.7rem 0.9rem; }
    div[data-testid="stMetric"] label { color: #a8a29e !important; font-size: 0.63rem !important; text-transform: uppercase; letter-spacing: 0.05em; }

    .stTabs [data-baseweb="tab-list"] { gap: 0; background: #f5f5f4; border-radius: 8px; padding: 3px; border: 1px solid #ebe9e7; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px; font-weight: 450; font-size: 0.78rem; color: #78716c; }
    .stTabs [aria-selected="true"] { background: #fff !important; color: #1c1917 !important; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }

    .stTextInput input { border: 1px solid #ebe9e7 !important; border-radius: 8px !important; font-size: 0.88rem !important; padding: 0.6rem 0.9rem !important; }
    .stTextInput input:focus { border-color: #4338ca !important; box-shadow: 0 0 0 3px rgba(67,56,202,0.08) !important; }

    footer { visibility: hidden; }
    hr { border: none; border-top: 1px solid #ebe9e7; margin: 1.5rem 0; }
    .src { font-size: 0.58rem; color: #c4c0bc; text-transform: uppercase; letter-spacing: 0.05em; }

    /* Download buttons */
    .stDownloadButton button { background: #fff !important; border: 1px solid #ebe9e7 !important;
        color: #57534e !important; font-size: 0.78rem !important; border-radius: 6px !important; }
    .stDownloadButton button:hover { border-color: #4338ca !important; color: #4338ca !important; }
    </style>
    """, unsafe_allow_html=True)


def t(text, c="m"):
    return f'<span class="lt lt-{c}">{text}</span>'


def src(text):
    return f'<span class="src">{text}</span>'


def footer():
    return f"""<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid #ebe9e7;">
        <p style="font-size:0.62rem;color:#a8a29e;text-align:center;letter-spacing:0.02em;line-height:1.8;">
            {LOGO_HTML} · Tulane University · Department of Political Science · 2026
        </p></div>"""


def page_head(title, subtitle):
    return f"""<p style="font-size:0.6rem;color:#a8a29e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.3rem;">
        {LOGO_HTML}</p>
        <h1 style="font-size:2rem;margin-bottom:0.15rem;">{title}</h1>
        <p style="color:#78716c;font-size:0.85rem;margin-bottom:1.25rem;">{subtitle}</p>"""
