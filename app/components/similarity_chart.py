"""Bill similarity display component."""

import streamlit as st

from analysis.similarity import find_similar_bills


def render_similar_bills(bill_id: int, limit: int = 5):
    """Show bills most similar to the given bill."""
    try:
        similar = find_similar_bills(bill_id, limit=limit)
    except Exception:
        st.info("Similarity data not available. Run embedding generation first.")
        return

    if not similar:
        st.info("No similar bills found.")
        return

    st.markdown("#### Similar Bills")

    for bill in similar:
        score = bill.get("similarity_score", 0)
        score_pct = f"{score:.0%}"

        col1, col2 = st.columns([1, 5])
        with col1:
            if score >= 0.8:
                st.markdown(f":red[**{score_pct}**]")
            elif score >= 0.6:
                st.markdown(f":orange[**{score_pct}**]")
            else:
                st.markdown(f"**{score_pct}**")
        with col2:
            st.markdown(f"**{bill['bill_number']}** — {bill['title'][:80]}")
            if bill.get("plain_english"):
                st.caption(bill["plain_english"][:150] + "...")
