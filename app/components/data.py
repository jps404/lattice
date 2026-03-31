"""Cached data queries for the LATTICE frontend."""

import streamlit as st
from ingestion.db import get_connection, get_cursor


@st.cache_data(ttl=120)
def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SQL query and return results as list of dicts. Cached for 2 minutes."""
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=120)
def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Run a SQL query and return first result. Cached for 2 minutes."""
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


@st.cache_data(ttl=120)
def count(table: str) -> int:
    """Get row count for a table. Cached."""
    r = query_one(f"SELECT COUNT(*) as c FROM {table}")
    return r["c"] if r else 0
