"""Shared database connection helper."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_db_url():
    """Get database URL from env vars or Streamlit secrets."""
    url = os.environ.get("SUPABASE_DB_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets["SUPABASE_DB_URL"]
    except Exception:
        raise RuntimeError("SUPABASE_DB_URL not found in environment or Streamlit secrets")


def get_connection():
    """Return a psycopg2 connection to the Supabase PostgreSQL database."""
    return psycopg2.connect(_get_db_url())


def get_cursor(conn):
    """Return a dict cursor for easier row access."""
    return conn.cursor(cursor_factory=RealDictCursor)
