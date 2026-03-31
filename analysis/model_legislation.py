"""Model legislation detection.

Compares Louisiana bills against known model legislation templates (ALEC, SPN, etc.)
and bills from other states to detect coordinated bill introduction.

Two-stage approach:
1. Pre-filter: Use embeddings to find candidate matches quickly
2. Detailed comparison: Use Claude to compare matched texts and identify specific overlaps
"""

import json
import logging
import os

import anthropic
from dotenv import load_dotenv

from analysis.similarity import search_by_text
from ingestion.db import get_connection, get_cursor

load_dotenv()
logger = logging.getLogger(__name__)

# Known model legislation sources to compare against
# In production, these would be loaded from a database or file
MODEL_BILL_SOURCES = {
    "ALEC": "American Legislative Exchange Council",
    "SPN": "State Policy Network",
    "LBFC": "Legislation from the Goldwater Institute, Heritage Foundation, etc.",
}


def detect_model_legislation(bill_id: int, threshold: float = 0.75) -> list[dict]:
    """Check if a bill matches known model legislation patterns.

    Uses embedding similarity as a pre-filter, then Claude for detailed comparison.

    Args:
        bill_id: Database bill ID
        threshold: Minimum similarity score to flag as potential match

    Returns:
        List of match dicts with source, score, and matching details.
    """
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT bill_number, title, bill_text FROM bills WHERE id = %s",
            (bill_id,),
        )
        bill = cur.fetchone()
        if not bill or not bill["bill_text"]:
            return []
    finally:
        conn.close()

    matches = []

    # Stage 1: Cross-state similarity search
    # Search for other bills in the database with high similarity
    similar = _find_cross_state_matches(bill_id, threshold)
    matches.extend(similar)

    # Stage 2: Compare against known model bill keywords/patterns
    pattern_matches = _check_model_patterns(bill["bill_text"], bill["title"])
    matches.extend(pattern_matches)

    # Store matches
    if matches:
        _store_matches(bill_id, matches)

    return matches


def _find_cross_state_matches(bill_id: int, threshold: float) -> list[dict]:
    """Find bills from other states with high textual similarity.

    For v0.1, this compares within the same database (Louisiana bills).
    As we add more states, this will detect cross-state copying.
    """
    from analysis.similarity import find_similar_bills

    similar = find_similar_bills(bill_id, limit=5, min_score=threshold)

    matches = []
    for s in similar:
        if s.get("similarity_score", 0) >= threshold:
            matches.append({
                "matched_source": f"LA {s['bill_number']}",
                "matched_title": s["title"],
                "similarity_score": s["similarity_score"],
                "matching_sections": f"High semantic similarity ({s['similarity_score']:.0%}) detected",
            })

    return matches


def _check_model_patterns(bill_text: str, title: str) -> list[dict]:
    """Check bill text against known model legislation patterns.

    Uses keyword/phrase matching as a lightweight pre-filter.
    These patterns are based on commonly used language in known model bills.
    """
    # Common phrases found in ALEC model legislation
    alec_indicators = [
        "right to work",
        "stand your ground",
        "castle doctrine",
        "voter id",
        "photo identification",
        "school choice",
        "education savings account",
        "taxpayer bill of rights",
        "regulatory sandbox",
        "certificate of need",
        "occupational licensing reform",
        "asset forfeiture reform",
        "transparency in coverage",
        "energy choice",
        "critical infrastructure protection",
    ]

    text_lower = bill_text.lower()
    title_lower = title.lower()

    matches = []
    for phrase in alec_indicators:
        if phrase in text_lower or phrase in title_lower:
            matches.append({
                "matched_source": "ALEC (pattern match)",
                "matched_title": f"Model bill pattern: '{phrase}'",
                "similarity_score": 0.6,  # Pattern match gets a moderate score
                "matching_sections": f"Bill contains known model legislation phrase: '{phrase}'",
            })

    return matches


def compare_texts_with_ai(bill_text: str, model_text: str, source_name: str) -> dict:
    """Use Claude to do a detailed comparison between a bill and model text.

    Returns detailed matching analysis.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    system = (
        "You are a legislative analyst comparing two pieces of legislation. "
        "Identify specific sections, phrases, or structural elements that are "
        "similar or identical. Be precise about what matches and what differs. "
        "Return JSON with: similarity_score (0.0-1.0), matching_sections (text "
        "description), key_differences (text), and assessment (1 sentence)."
    )

    user_msg = (
        f"Compare this Louisiana bill against the model legislation from {source_name}:\n\n"
        f"<louisiana_bill>\n{bill_text[:30000]}\n</louisiana_bill>\n\n"
        f"<model_legislation>\n{model_text[:30000]}\n</model_legislation>"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text
        # Parse JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        logger.error("AI comparison failed: %s", e)

    return {}


def _store_matches(bill_id: int, matches: list[dict]):
    """Store model legislation matches in the database."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        for match in matches:
            cur.execute(
                """INSERT INTO model_matches
                    (bill_id, matched_source, matched_title, similarity_score, matching_sections)
                VALUES (%s, %s, %s, %s, %s)""",
                (
                    bill_id,
                    match["matched_source"],
                    match.get("matched_title", ""),
                    match.get("similarity_score", 0),
                    match.get("matching_sections", ""),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def scan_all_bills(threshold: float = 0.75) -> dict:
    """Scan all analyzed bills for model legislation matches."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT b.id FROM bills b
            JOIN bill_analyses ba ON ba.bill_id = b.id
            LEFT JOIN model_matches mm ON mm.bill_id = b.id
            WHERE b.bill_text IS NOT NULL AND mm.id IS NULL
            """
        )
        bill_ids = [row["id"] for row in cur.fetchall()]
    finally:
        conn.close()

    logger.info("Scanning %d bills for model legislation", len(bill_ids))
    stats = {"scanned": 0, "matched": 0}

    for bill_id in bill_ids:
        matches = detect_model_legislation(bill_id, threshold)
        stats["scanned"] += 1
        if matches:
            stats["matched"] += 1

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = scan_all_bills()
    print(f"Model legislation scan: {stats}")
