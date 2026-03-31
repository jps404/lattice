"""Shared database connection helper."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _get_db_url():
    """Get database URL from env vars or Streamlit secrets."""
    # Try environment variable first (local dev)
    url = os.environ.get("SUPABASE_DB_URL")
    if url:
        return url
    # Try Streamlit secrets (cloud deployment)
    try:
        import streamlit as st
        if "SUPABASE_DB_URL" in st.secrets:
            return st.secrets["SUPABASE_DB_URL"]
        if "db" in st.secrets:
            return st.secrets["db"]["url"]
    except Exception:
        pass
    raise RuntimeError("Database URL not found")


def get_connection():
    """Return a psycopg2 connection to the Supabase PostgreSQL database."""
    return psycopg2.connect(_get_db_url())


def get_cursor(conn):
    """Return a dict cursor for easier row access."""
    return conn.cursor(cursor_factory=RealDictCursor)
