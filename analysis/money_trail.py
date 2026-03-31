"""Money trail mapper — connects campaign donors to legislation.

For each bill, looks at the sponsor's top donors by industry and checks
whether the bill's policy area and beneficiaries align with donor interests.
Generates conflict flags when patterns are detected.
"""

import json
import logging

from analysis.bill_analyzer import BillAnalyzer
from ingestion.db import get_connection, get_cursor

logger = logging.getLogger(__name__)


def get_sponsor_donors(bill_id: int, limit: int = 30) -> list[dict]:
    """Get top donors for a bill's primary sponsor, grouped by industry."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT c.donor_name, c.donor_industry, c.donor_sector,
                   c.contributor_type, SUM(c.amount) as total_amount,
                   COUNT(*) as contribution_count
            FROM contributions c
            JOIN sponsorships s ON s.legislator_id = c.legislator_id
            WHERE s.bill_id = %s AND s.sponsor_type = 'Primary'
            GROUP BY c.donor_name, c.donor_industry, c.donor_sector, c.contributor_type
            ORDER BY total_amount DESC
            LIMIT %s
            """,
            (bill_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_sponsor_industry_totals(bill_id: int) -> list[dict]:
    """Get total donations to a bill's primary sponsor by industry."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT c.donor_industry, c.donor_sector,
                   SUM(c.amount) as total_amount,
                   COUNT(DISTINCT c.donor_name) as donor_count
            FROM contributions c
            JOIN sponsorships s ON s.legislator_id = c.legislator_id
            WHERE s.bill_id = %s AND s.sponsor_type = 'Primary'
              AND c.donor_industry IS NOT NULL AND c.donor_industry != ''
            GROUP BY c.donor_industry, c.donor_sector
            ORDER BY total_amount DESC
            LIMIT 20
            """,
            (bill_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_sponsor_info(bill_id: int) -> dict | None:
    """Get the primary sponsor's info for a bill."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT l.id, l.name, l.party, l.district, l.role
            FROM legislators l
            JOIN sponsorships s ON s.legislator_id = l.id
            WHERE s.bill_id = %s AND s.sponsor_type = 'Primary'
            LIMIT 1
            """,
            (bill_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def analyze_money_trail(bill_id: int) -> dict:
    """Run Pass 3 money trail analysis for a single bill.

    Requires:
    - Bill already analyzed (bill_analyses row exists)
    - Campaign finance data loaded for the sponsor

    Returns analysis result dict or empty dict if prerequisites missing.
    """
    conn = get_connection()
    try:
        cur = get_cursor(conn)

        # Get bill analysis
        cur.execute(
            "SELECT plain_english, policy_area, who_benefits FROM bill_analyses WHERE bill_id = %s",
            (bill_id,),
        )
        analysis = cur.fetchone()
        if not analysis:
            logger.warning("Bill %d has no analysis — run Pass 2 first", bill_id)
            return {}
    finally:
        conn.close()

    # Get sponsor info
    sponsor = get_sponsor_info(bill_id)
    if not sponsor:
        logger.warning("Bill %d has no primary sponsor", bill_id)
        return {}

    # Get donor data
    donors = get_sponsor_donors(bill_id)
    if not donors:
        logger.info("No donor data for sponsor of bill %d", bill_id)
        return {}

    # Format donors for the AI
    donor_list = [
        {
            "name": d["donor_name"],
            "industry": d["donor_industry"],
            "sector": d["donor_sector"],
            "amount": float(d["total_amount"]),
            "type": d["contributor_type"],
        }
        for d in donors
    ]

    # Run Pass 3 via BillAnalyzer
    analyzer = BillAnalyzer()
    result = analyzer.pass3_money_trail(
        plain_english=analysis["plain_english"],
        policy_area=analysis["policy_area"],
        sponsor_name=sponsor["name"],
        sponsor_party=sponsor["party"] or "",
        sponsor_district=sponsor["district"] or "",
        top_donors=donor_list,
        who_benefits=analysis["who_benefits"],
    )

    if not result:
        return {}

    # Store conflict flags if any
    flags = result.get("conflict_flags", [])
    alignment_score = result.get("donor_alignment_score", 0)

    if flags or alignment_score > 0.5:
        _store_conflict_flags(bill_id, sponsor["id"], result)

    return result


def _store_conflict_flags(bill_id: int, legislator_id: int, analysis: dict):
    """Store detected conflict flags in the database."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)

        alignment_score = analysis.get("donor_alignment_score", 0)
        flags = analysis.get("conflict_flags", [])
        aligned_donors = analysis.get("aligned_donors", [])

        # Determine severity
        if alignment_score >= 0.8:
            severity = "high"
        elif alignment_score >= 0.5:
            severity = "medium"
        else:
            severity = "low"

        for flag_text in flags:
            cur.execute(
                """INSERT INTO conflict_flags
                    (bill_id, legislator_id, flag_type, description, severity, evidence)
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    bill_id,
                    legislator_id,
                    "donor_alignment",
                    flag_text,
                    severity,
                    json.dumps({
                        "alignment_score": alignment_score,
                        "aligned_donors": aligned_donors,
                        "assessment": analysis.get("assessment", ""),
                    }),
                ),
            )

        conn.commit()
        logger.info("Stored %d conflict flags for bill %d", len(flags), bill_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_all_money_trails() -> dict:
    """Run money trail analysis for all analyzed bills with sponsor donor data."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT DISTINCT ba.bill_id
            FROM bill_analyses ba
            JOIN sponsorships s ON s.bill_id = ba.bill_id AND s.sponsor_type = 'Primary'
            JOIN contributions c ON c.legislator_id = s.legislator_id
            LEFT JOIN conflict_flags cf ON cf.bill_id = ba.bill_id
            WHERE cf.id IS NULL
            """
        )
        bill_ids = [row["bill_id"] for row in cur.fetchall()]
    finally:
        conn.close()

    logger.info("Running money trail analysis on %d bills", len(bill_ids))
    stats = {"analyzed": 0, "flagged": 0, "skipped": 0}

    for bill_id in bill_ids:
        try:
            result = analyze_money_trail(bill_id)
            if result:
                stats["analyzed"] += 1
                if result.get("conflict_flags"):
                    stats["flagged"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error("Error on bill %d: %s", bill_id, e)
            stats["skipped"] += 1

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = run_all_money_trails()
    print(f"Money trail analysis: {stats}")
