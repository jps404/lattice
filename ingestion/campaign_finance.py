"""FollowTheMoney API client for campaign contribution data.

The FTM API uses flat query parameters, not RESTful paths.
Base endpoint: https://api.followthemoney.org/
Key params: dt (data type), s (state), c-exi (candidate entity ID), gro (group by)

Pulls donor/contribution records for Louisiana legislators and stores them
in the contributions table. Cross-references legislators via ftm_eid
(provided by LegiScan's getPerson endpoint).

Rate limit: ~1 request/second (conservative).
License: CC BY-NC-SA 3.0.
"""

import os
import time
import logging

import requests
from dotenv import load_dotenv

from ingestion.db import get_connection, get_cursor

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = "https://api.followthemoney.org/"


class FollowTheMoneyClient:
    """Client for the FollowTheMoney API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("FOLLOWTHEMONEY_API_KEY", "")
        self._last_request_time = 0.0

    def _request(self, **params) -> dict:
        """Make a rate-limited request to the FTM API."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        params["APIKey"] = self.api_key
        params["mode"] = "json"

        for attempt in range(3):
            try:
                resp = requests.get(BASE_URL, params=params, timeout=120)
                resp.raise_for_status()
                self._last_request_time = time.time()
                return resp.json()
            except requests.RequestException as e:
                logger.warning("FTM request attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise

    # ── Contribution fetching ──────────────────────────────────────

    def get_contributions_by_donor(self, eid: str, page: int = 1) -> list[dict]:
        """Get contributions for a candidate grouped by donor.

        Uses dt=1 (contributions), c-exi (candidate entity ID), gro (group by contributor).

        Args:
            eid: FollowTheMoney candidate entity ID
            page: Page number for pagination

        Returns:
            List of contribution records with donor info and totals.
        """
        data = self._request(
            dt="1",
            **{"c-exi": eid},
            gro="d-id",  # Group by donor ID
            p=str(page),
        )
        records = data.get("records", [])
        if isinstance(records, dict):
            records = [records]
        return records

    def get_contributions_by_industry(self, eid: str) -> list[dict]:
        """Get contributions for a candidate grouped by industry.

        Args:
            eid: FollowTheMoney candidate entity ID

        Returns:
            List of industry-level contribution summaries.
        """
        data = self._request(
            dt="1",
            **{"c-exi": eid},
            gro="d-cci",  # Group by general industry
        )
        records = data.get("records", [])
        if isinstance(records, dict):
            records = [records]
        return records

    def get_candidate_summary(self, eid: str) -> dict | None:
        """Get summary info for a candidate by entity ID."""
        data = self._request(
            dt="1",
            **{"c-exi": eid},
        )
        records = data.get("records", [])
        if isinstance(records, dict):
            records = [records]
        return records[0] if records else None

    # ── Database sync ──────────────────────────────────────────────

    def sync_legislator_contributions(self, legislator_id: int, ftm_eid: str) -> int:
        """Fetch and store contributions for a single legislator.

        Fetches by donor, then by industry for richer data.
        Returns number of contributions inserted.
        """
        logger.info("Fetching contributions for legislator %d (eid=%s)", legislator_id, ftm_eid)

        # Get contributions grouped by donor
        try:
            records = self.get_contributions_by_donor(ftm_eid)
        except Exception as e:
            logger.error("Failed to fetch contributions for eid %s: %s", ftm_eid, e)
            return 0

        if not records:
            logger.info("No contributions found for eid %s", ftm_eid)
            return 0

        # Also get industry breakdown for sector/industry tagging
        industry_map = {}
        try:
            industry_records = self.get_contributions_by_industry(ftm_eid)
            for rec in industry_records:
                # Build lookup from industry records
                industry_name = rec.get("General_Industry", rec.get("Broad_Sector", ""))
                if industry_name:
                    industry_map[industry_name] = rec.get("Broad_Sector", "")
        except Exception:
            pass  # Industry data is supplemental, don't fail

        conn = get_connection()
        count = 0
        try:
            cur = get_cursor(conn)

            for rec in records:
                # Parse amount — FTM returns "Total_$" as a string like "$1,234.56"
                amount_str = rec.get("Total_$", rec.get("amount", "0"))
                try:
                    amount = float(str(amount_str).replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    amount = 0

                num_records = rec.get("#_of_Records", "1")
                try:
                    num_records = int(str(num_records).replace(",", ""))
                except (ValueError, TypeError):
                    num_records = 1

                donor_name = rec.get("Contributor", rec.get("Donor", "Unknown"))
                # FTM sometimes returns "name||id" format
                if "||" in str(donor_name):
                    donor_name = donor_name.split("||")[0]

                industry = rec.get("General_Industry", rec.get("Broad_Sector", ""))
                if "||" in str(industry):
                    industry = industry.split("||")[0]

                sector = rec.get("Broad_Sector", "")
                if "||" in str(sector):
                    sector = sector.split("||")[0]

                contributor_type = rec.get("Contributor_Type", rec.get("Entity_Type", ""))
                if "||" in str(contributor_type):
                    contributor_type = contributor_type.split("||")[0]

                cur.execute(
                    """INSERT INTO contributions
                        (legislator_id, donor_name, donor_industry, donor_sector,
                         amount, contributor_type)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        legislator_id,
                        donor_name,
                        industry,
                        sector,
                        amount,
                        contributor_type,
                    ),
                )
                count += 1

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        logger.info("Inserted %d contributions for legislator %d", count, legislator_id)
        return count

    def sync_all_legislators(self) -> dict:
        """Fetch contributions for ALL legislators that have an ftm_eid.

        Returns summary stats.
        """
        conn = get_connection()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                SELECT id, ftm_eid, name FROM legislators
                WHERE ftm_eid IS NOT NULL AND ftm_eid != ''
            """)
            legislators = cur.fetchall()
        finally:
            conn.close()

        logger.info("Found %d legislators with ftm_eid", len(legislators))
        stats = {"legislators_processed": 0, "total_contributions": 0, "errors": 0}

        for leg in legislators:
            try:
                count = self.sync_legislator_contributions(leg["id"], leg["ftm_eid"])
                stats["total_contributions"] += count
                stats["legislators_processed"] += 1
            except Exception as e:
                logger.error("Error syncing %s: %s", leg["name"], e)
                stats["errors"] += 1

        logger.info("Campaign finance sync complete: %s", stats)
        return stats


# ── CLI entrypoint ─────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = FollowTheMoneyClient()
    stats = client.sync_all_legislators()
    print(f"Done! {stats}")
