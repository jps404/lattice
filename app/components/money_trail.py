"""Money trail visualization component."""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from ingestion.db import get_connection, get_cursor


def render_donor_chart(legislator_id: int):
    """Render a bar chart of top donors by industry for a legislator."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT donor_industry, SUM(amount) as total,
                   COUNT(DISTINCT donor_name) as donor_count
            FROM contributions
            WHERE legislator_id = %s
              AND donor_industry IS NOT NULL AND donor_industry != ''
            GROUP BY donor_industry
            ORDER BY total DESC
            LIMIT 15
            """,
            (legislator_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        st.info("No donor industry data available for this legislator.")
        return

    df = pd.DataFrame(rows)
    df["total"] = df["total"].astype(float)

    fig = px.bar(
        df,
        x="total",
        y="donor_industry",
        orientation="h",
        labels={"total": "Total Contributions ($)", "donor_industry": "Industry"},
        color="total",
        color_continuous_scale="Reds",
    )
    fig.update_layout(
        showlegend=False,
        height=400,
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_top_donors_table(legislator_id: int, limit: int = 20):
    """Render a table of top individual donors."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT donor_name, donor_industry, donor_employer,
                   SUM(amount) as total, COUNT(*) as num_contributions,
                   contributor_type
            FROM contributions
            WHERE legislator_id = %s
            GROUP BY donor_name, donor_industry, donor_employer, contributor_type
            ORDER BY total DESC
            LIMIT %s
            """,
            (legislator_id, limit),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        st.info("No contribution data available.")
        return

    df = pd.DataFrame(rows)
    df["total"] = df["total"].apply(lambda x: f"${float(x):,.0f}")
    df.columns = ["Donor", "Industry", "Employer", "Total", "# Contributions", "Type"]
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_conflict_flags(bill_id: int | None = None, legislator_id: int | None = None):
    """Render conflict flags for a bill or legislator."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)

        if bill_id:
            cur.execute(
                """
                SELECT cf.*, l.name as legislator_name, b.bill_number
                FROM conflict_flags cf
                JOIN legislators l ON l.id = cf.legislator_id
                JOIN bills b ON b.id = cf.bill_id
                WHERE cf.bill_id = %s
                ORDER BY cf.severity DESC
                """,
                (bill_id,),
            )
        elif legislator_id:
            cur.execute(
                """
                SELECT cf.*, l.name as legislator_name, b.bill_number
                FROM conflict_flags cf
                JOIN legislators l ON l.id = cf.legislator_id
                JOIN bills b ON b.id = cf.bill_id
                WHERE cf.legislator_id = %s
                ORDER BY cf.severity DESC
                """,
                (legislator_id,),
            )
        else:
            return

        flags = cur.fetchall()
    finally:
        conn.close()

    if not flags:
        st.success("No conflict flags detected.")
        return

    for flag in flags:
        severity = flag["severity"]
        icon = {"high": ":red_circle:", "medium": ":orange_circle:", "low": ":white_circle:"}.get(severity, "")

        st.markdown(f"{icon} **{severity.upper()}** — {flag['description']}")

        evidence = flag.get("evidence")
        if evidence:
            if isinstance(evidence, str):
                evidence = json.loads(evidence)
            if evidence.get("assessment"):
                st.caption(evidence["assessment"])
