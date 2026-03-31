"""Import campaign finance data from FollowTheMoney CSV export.

Since the FTM API is unreliable, this script imports data from their
bulk CSV download. Go to followthemoney.org, search for Louisiana
candidates, and export as CSV.

Usage:
    PYTHONPATH=. uv run python scripts/import_ftm_csv.py contributions.csv
"""

import argparse
import csv
import logging
import sys

from ingestion.db import get_connection, get_cursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def import_csv(filepath: str) -> dict:
    """Import a FTM CSV file into the contributions table.

    Tries to match donors to legislators by name (fuzzy matching on
    candidate name to legislator name).
    """
    conn = get_connection()
    cur = get_cursor(conn)

    # Build legislator name lookup
    cur.execute("SELECT id, name, first_name, last_name FROM legislators")
    legislators = cur.fetchall()
    name_map = {}
    for leg in legislators:
        # Index by last name for fuzzy matching
        last = (leg.get("last_name") or "").lower().strip()
        full = (leg.get("name") or "").lower().strip()
        if last:
            name_map[last] = leg["id"]
        if full:
            name_map[full] = leg["id"]

    stats = {"rows": 0, "matched": 0, "unmatched": 0, "inserted": 0}

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats["rows"] += 1

            # Try to find the candidate in our legislators table
            candidate = row.get("Candidate", row.get("candidate", "")).lower().strip()
            leg_id = None

            # Try exact match first
            if candidate in name_map:
                leg_id = name_map[candidate]
            else:
                # Try last name match
                parts = candidate.split(",")
                if parts:
                    last = parts[0].strip()
                    if last in name_map:
                        leg_id = name_map[last]

            if not leg_id:
                stats["unmatched"] += 1
                continue

            stats["matched"] += 1

            # Parse amount
            amount_str = row.get("Amount", row.get("amount", row.get("Total_$", "0")))
            try:
                amount = float(str(amount_str).replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                amount = 0

            donor = row.get("Contributor", row.get("Donor", row.get("contributor", "Unknown")))
            industry = row.get("General_Industry", row.get("Industry", row.get("Broad_Sector", "")))
            sector = row.get("Broad_Sector", row.get("Sector", ""))
            contrib_type = row.get("Contributor_Type", row.get("Entity_Type", ""))
            date = row.get("Date", row.get("date", None))
            year = row.get("Election_Year", row.get("election_year", None))

            cur.execute(
                """INSERT INTO contributions
                    (legislator_id, donor_name, donor_industry, donor_sector,
                     amount, contribution_date, election_year, contributor_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (leg_id, donor, industry, sector, amount, date or None, year or None, contrib_type),
            )
            stats["inserted"] += 1

            if stats["inserted"] % 500 == 0:
                conn.commit()
                logger.info("  ...%d inserted", stats["inserted"])

    conn.commit()
    conn.close()

    logger.info("Import complete: %s", stats)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import FTM CSV into LATTICE")
    parser.add_argument("csvfile", help="Path to the FTM CSV export file")
    args = parser.parse_args()

    stats = import_csv(args.csvfile)
    print(f"Done! {stats['inserted']} contributions imported, {stats['unmatched']} unmatched candidates")
