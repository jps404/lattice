"""Scrape campaign finance contributions from Louisiana Ethics Administration.

Pulls electronic filing contribution data for all matched legislators
from ethics.la.gov and stores in the contributions table.

Usage:
    PYTHONPATH=. uv run python scripts/scrape_la_ethics.py
    PYTHONPATH=. uv run python scripts/scrape_la_ethics.py --limit 10
"""

import argparse
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from ingestion.db import get_connection, get_cursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.ethics.la.gov/CampaignFinanceSearch/SearchEFilingContributors.aspx"


def get_filer_map() -> dict:
    """Get mapping of filer names to CAN IDs from the Ethics search page."""
    session = requests.Session()
    resp = session.get(BASE_URL, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")
    select = soup.find("select")
    return {
        opt.text.strip().lower(): opt.get("value")
        for opt in select.find_all("option")
    }


def match_legislators(filer_map: dict) -> list[tuple]:
    """Match our legislators to LA Ethics filer IDs."""
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute("SELECT id, name, first_name, last_name FROM legislators")
    legs = cur.fetchall()
    conn.close()

    matches = []
    for leg in legs:
        last = (leg.get("last_name") or "").strip()
        first = (leg.get("first_name") or "").strip()
        if not last:
            continue

        for filer_name, filer_id in filer_map.items():
            if not filer_id.startswith("CAN"):
                continue
            if last.lower() in filer_name and first.lower()[:3] in filer_name:
                matches.append((leg["id"], leg["name"], filer_id))
                break

    return matches


def scrape_contributions(filer_id: str) -> list[dict]:
    """Scrape contribution records for a specific filer from LA Ethics."""
    session = requests.Session()

    # First get the page to get ASP.NET form state
    resp = session.get(BASE_URL, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract ASP.NET state fields
    form_data = {}
    for field in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        inp = soup.find("input", {"name": field})
        if inp:
            form_data[field] = inp.get("value", "")

    # Find the select element and its name
    select = soup.find("select")
    select_name = select.get("name", "") if select else ""

    # Submit search for this filer
    form_data[select_name] = filer_id
    # Find the search button
    submit_btn = soup.find("input", {"type": "submit"}) or soup.find("button")
    if submit_btn:
        btn_name = submit_btn.get("name", "")
        if btn_name:
            form_data[btn_name] = submit_btn.get("value", "Search")

    try:
        resp = session.post(BASE_URL, data=form_data, timeout=60)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Failed to submit search for %s: %s", filer_id, e)
        return []

    # Parse results table
    table = soup.find("table", {"id": lambda x: x and "grid" in str(x).lower()})
    if not table:
        # Try finding any data table
        tables = soup.find_all("table")
        for t in tables:
            if t.find("th") and len(t.find_all("tr")) > 2:
                table = t
                break

    if not table:
        return []

    # Get headers
    headers = []
    header_row = table.find("tr")
    if header_row:
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    contributions = []
    rows = table.find_all("tr")[1:]  # Skip header

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        record = {}
        for i, cell in enumerate(cells):
            if i < len(headers):
                record[headers[i]] = cell.get_text(strip=True)

        contributions.append(record)

    return contributions


def import_contributions(legislator_id: int, records: list[dict]) -> int:
    """Store scraped contributions in the database."""
    if not records:
        return 0

    conn = get_connection()
    cur = get_cursor(conn)
    count = 0

    for rec in records:
        # Try to parse amount from various field names
        amount_str = (
            rec.get("amount", "") or rec.get("contribution amount", "") or
            rec.get("total", "") or "0"
        )
        amount_str = re.sub(r"[^\d.]", "", amount_str)
        try:
            amount = float(amount_str) if amount_str else 0
        except ValueError:
            amount = 0

        donor = (
            rec.get("contributor", "") or rec.get("contributor name", "") or
            rec.get("name", "") or "Unknown"
        )
        date = rec.get("date", "") or rec.get("contribution date", "") or None

        cur.execute(
            """INSERT INTO contributions
                (legislator_id, donor_name, amount, contribution_date, contributor_type)
            VALUES (%s, %s, %s, %s, %s)""",
            (legislator_id, donor, amount, date if date else None, "Individual"),
        )
        count += 1

    conn.commit()
    conn.close()
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Max legislators to process")
    args = parser.parse_args()

    logger.info("Loading filer list from LA Ethics...")
    filer_map = get_filer_map()
    logger.info("Found %d filers", len(filer_map))

    matches = match_legislators(filer_map)
    logger.info("Matched %d legislators to filer IDs", len(matches))

    if args.limit:
        matches = matches[:args.limit]

    total = 0
    for leg_id, name, filer_id in matches:
        logger.info("Scraping %s (%s)...", name, filer_id)
        try:
            records = scrape_contributions(filer_id)
            if records:
                count = import_contributions(leg_id, records)
                total += count
                logger.info("  %d contributions", count)
            else:
                logger.info("  No records found")
        except Exception as e:
            logger.warning("  Error: %s", e)

        time.sleep(1)  # Be polite

    logger.info("Done! %d total contributions imported", total)


if __name__ == "__main__":
    main()
