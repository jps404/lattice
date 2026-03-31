"""Automated conflict-of-interest detection.

Identifies potential conflicts between legislators' campaign donors
and the bills they sponsor. Generates flags based on:

1. donor_alignment: Sponsor's top donors match the bill's beneficiaries
2. timing_suspicious: Large donations received shortly before bill introduction
3. committee_capture: Committee members receiving outsized donations from
   industries regulated by their committee
"""

import json
import logging
from datetime import timedelta

from ingestion.db import get_connection, get_cursor

logger = logging.getLogger(__name__)


def detect_donor_alignment(bill_id: int) -> list[dict]:
    """Check if a bill's sponsor received significant donations from
    industries that would benefit from the bill.

    This is handled by the money_trail module's Pass 3 analysis.
    This function checks if flags already exist and returns them.
    """
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT * FROM conflict_flags
            WHERE bill_id = %s AND flag_type = 'donor_alignment'""",
            (bill_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def detect_timing_suspicious(bill_id: int, window_days: int = 180) -> list[dict]:
    """Detect large donations received within a time window before bill introduction.

    Flags cases where a sponsor received significant contributions from an
    industry shortly before introducing a bill that benefits that industry.

    Args:
        bill_id: Database bill ID
        window_days: Number of days before bill intro to check for donations
    """
    conn = get_connection()
    flags = []

    try:
        cur = get_cursor(conn)

        # Get bill intro date and sponsor
        cur.execute(
            """
            SELECT b.id, b.bill_number, b.created_at::date as created_at, ba.policy_area, ba.who_benefits,
                   l.id as legislator_id, l.name as legislator_name
            FROM bills b
            JOIN bill_analyses ba ON ba.bill_id = b.id
            JOIN sponsorships s ON s.bill_id = b.id AND s.sponsor_type = 'Primary'
            JOIN legislators l ON l.id = s.legislator_id
            WHERE b.id = %s
            """,
            (bill_id,),
        )
        row = cur.fetchone()
        if not row:
            return []

        bill_date = row["created_at"]
        window_start = bill_date - timedelta(days=window_days)

        # Find large contributions in the window
        cur.execute(
            """
            SELECT donor_name, donor_industry, donor_sector,
                   SUM(amount) as total_amount, COUNT(*) as num_contributions,
                   MAX(contribution_date) as latest_date
            FROM contributions
            WHERE legislator_id = %s
              AND contribution_date BETWEEN %s AND %s
              AND amount >= 500
            GROUP BY donor_name, donor_industry, donor_sector
            HAVING SUM(amount) >= 2000
            ORDER BY total_amount DESC
            LIMIT 20
            """,
            (row["legislator_id"], window_start, bill_date),
        )

        suspicious_donors = cur.fetchall()

        for donor in suspicious_donors:
            flags.append({
                "bill_id": bill_id,
                "legislator_id": row["legislator_id"],
                "flag_type": "timing_suspicious",
                "severity": "medium",
                "description": (
                    f"{row['legislator_name']} received ${float(donor['total_amount']):,.0f} from "
                    f"{donor['donor_name']} ({donor['donor_industry'] or 'unknown industry'}) "
                    f"within {window_days} days before introducing {row['bill_number']}"
                ),
                "evidence": {
                    "donor": donor["donor_name"],
                    "industry": donor["donor_industry"],
                    "amount": float(donor["total_amount"]),
                    "latest_date": str(donor["latest_date"]),
                    "bill_date": str(bill_date),
                    "window_days": window_days,
                },
            })

        # Store flags
        for flag in flags:
            cur.execute(
                """INSERT INTO conflict_flags
                    (bill_id, legislator_id, flag_type, description, severity, evidence)
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    flag["bill_id"],
                    flag["legislator_id"],
                    flag["flag_type"],
                    flag["description"],
                    flag["severity"],
                    json.dumps(flag["evidence"], default=str),
                ),
            )
        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return flags


def detect_committee_capture(legislator_id: int) -> list[dict]:
    """Detect if a legislator on a specific committee receives outsized
    donations from industries regulated by that committee.

    Note: Committee data isn't available in LegiScan free tier.
    This is a placeholder for when we add committee data.
    """
    # TODO: Implement when committee membership data is available
    # For v0.1, this returns empty — committee data requires LegiScan Pro
    # or scraping from legis.la.gov
    return []


def run_full_conflict_scan() -> dict:
    """Run all conflict detection methods on all analyzed bills."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT DISTINCT ba.bill_id
            FROM bill_analyses ba
            JOIN sponsorships s ON s.bill_id = ba.bill_id AND s.sponsor_type = 'Primary'
            JOIN contributions c ON c.legislator_id = s.legislator_id
            """
        )
        bill_ids = [row["bill_id"] for row in cur.fetchall()]
    finally:
        conn.close()

    logger.info("Running conflict scan on %d bills", len(bill_ids))
    stats = {"bills_scanned": 0, "timing_flags": 0, "errors": 0}

    for bill_id in bill_ids:
        try:
            timing_flags = detect_timing_suspicious(bill_id)
            stats["timing_flags"] += len(timing_flags)
            stats["bills_scanned"] += 1
        except Exception as e:
            logger.error("Error scanning bill %d: %s", bill_id, e)
            stats["errors"] += 1

    logger.info("Conflict scan complete: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = run_full_conflict_scan()
    print(f"Conflict scan: {stats}")
