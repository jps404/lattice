"""Louisiana Ethics Administration lobbyist data scraper.

Scrapes lobbyist registration data from the Louisiana Ethics Administration
website and stores it in the lobbyists table.

Source: https://ethics.la.gov/LobbyistData/
"""

import logging

import requests
from bs4 import BeautifulSoup

from ingestion.db import get_connection, get_cursor

logger = logging.getLogger(__name__)

LOBBYIST_URL = "https://ethics.la.gov/LobbyistData/ResultsByLobbyist.aspx"


def scrape_lobbyists() -> int:
    """Scrape lobbyist registrations from Louisiana Ethics.

    Note: The LA Ethics site may require form-based navigation.
    This is a best-effort scraper — the site structure may change.

    Returns number of lobbyists inserted.
    """
    logger.info("Scraping Louisiana lobbyist data...")

    # The LA Ethics site uses ASP.NET forms, which makes scraping complex.
    # For v0.1, we'll implement a basic scraper and enhance later.
    # If the site blocks scraping, we can fall back to manual CSV upload.

    try:
        session = requests.Session()
        resp = session.get(LOBBYIST_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to reach LA Ethics site: %s", e)
        logger.info("Lobbyist data will need to be loaded manually for v0.1")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")

    # Parse the lobbyist table — structure depends on the actual page
    # This is a placeholder that will need adjustment based on the real HTML
    rows = soup.select("table.gridview tr")[1:]  # Skip header row

    conn = get_connection()
    count = 0
    try:
        cur = get_cursor(conn)

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            name = cells[0].get_text(strip=True)
            firm = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            client = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            if not name:
                continue

            cur.execute(
                """INSERT INTO lobbyists (name, firm, client, source_url)
                VALUES (%s, %s, %s, %s)""",
                (name, firm, client, LOBBYIST_URL),
            )
            count += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info("Inserted %d lobbyist records", count)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    count = scrape_lobbyists()
    print(f"Done! Inserted {count} lobbyist records")
