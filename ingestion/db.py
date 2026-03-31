"""Shared database connection helper."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Return a psycopg2 connection to the Supabase PostgreSQL database."""
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


def get_cursor(conn):
    """Return a dict cursor for easier row access."""
    return conn.cursor(cursor_factory=RealDictCursor)
