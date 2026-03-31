"""Reusable bill display card component."""

import json

import streamlit as st


def render_bill_card(bill: dict, analysis: dict | None = None, expanded: bool = False):
    """Render a bill as an expandable card.

    Args:
        bill: Dict with bill data (bill_number, title, current_status, etc.)
        analysis: Optional dict with analysis data (plain_english, key_changes, etc.)
        expanded: Whether to show expanded view by default
    """
    status_colors = {
        "Introduced": "blue",
        "Engrossed": "orange",
        "Enrolled": "green",
        "Passed": "green",
        "Vetoed": "red",
        "Failed": "red",
    }

    status = bill.get("current_status", "Unknown")
    status_color = status_colors.get(status, "gray")

    # Header line
    header = f"**{bill['bill_number']}** — {bill.get('title', 'No title')}"

    with st.expander(header, expanded=expanded):
        # Status tags
        cols = st.columns([1, 1, 1, 2])
        with cols[0]:
            st.markdown(f":{status_color}[{status}]")
        with cols[1]:
            if analysis and analysis.get("policy_area"):
                st.caption(f"{analysis['policy_area']}")
        with cols[2]:
            if analysis and analysis.get("controversy_score") is not None:
                score = analysis["controversy_score"]
                if score >= 0.7:
                    st.markdown(f":red[Controversy: {score:.0%}]")
                elif score >= 0.4:
                    st.markdown(f":orange[Controversy: {score:.0%}]")
                else:
                    st.caption(f"Controversy: {score:.0%}")

        # Plain English summary — the star of the show
        if analysis and analysis.get("plain_english"):
            st.markdown("### What it actually does")
            st.info(analysis["plain_english"])

        # Key changes
        if analysis and analysis.get("key_changes"):
            changes = analysis["key_changes"]
            if isinstance(changes, str):
                try:
                    changes = json.loads(changes)
                except (json.JSONDecodeError, TypeError):
                    changes = [changes]
            if changes:
                st.markdown("**Key changes:**")
                for change in changes:
                    st.markdown(f"- {change}")

        # Impact
        col_a, col_b = st.columns(2)
        with col_a:
            if analysis and analysis.get("who_benefits"):
                st.markdown("**Who benefits:**")
                st.write(analysis["who_benefits"])
        with col_b:
            if analysis and analysis.get("who_is_harmed"):
                st.markdown("**Who is harmed:**")
                st.write(analysis["who_is_harmed"])

        # Official title and link
        st.markdown("---")
        st.caption(f"Official title: {bill.get('title', 'N/A')}")
        if bill.get("url"):
            st.markdown(f"[View original bill text]({bill['url']})")
