"""Shared database connection helper."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Load .env for local dev — silently skip on Streamlit Cloud
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def get_connection():
    """Return a psycopg2 connection to the Supabase PostgreSQL database."""
    # 1. Try environment variable (local dev with .env)
    url = os.environ.get("SUPABASE_DB_URL")
    if url:
        return psycopg2.connect(url)

    # 2. Try Streamlit secrets (cloud deployment)
    try:
        import streamlit as st
        if "SUPABASE_DB_URL" in st.secrets:
            return psycopg2.connect(st.secrets["SUPABASE_DB_URL"])
        if "db" in st.secrets and "url" in st.secrets["db"]:
            return psycopg2.connect(st.secrets["db"]["url"])
    except Exception:
        pass

    raise RuntimeError("No database URL found")


def get_cursor(conn):
    """Return a dict cursor for easier row access."""
    return conn.cursor(cursor_factory=RealDictCursor)
