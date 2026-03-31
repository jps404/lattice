"""LegiScan API client for pulling Louisiana legislative data.

Handles:
- Fetching session lists to find the current LA session
- Pulling the master bill list for a session
- Fetching full bill details (sponsors, history, texts, votes)
- Decoding base64 bill text
- Upserting everything into the database

Rate limit: ~2 requests/second. Free tier: 30,000 queries/month.
"""

import base64
import json
import os
import time
import logging

import requests
from dotenv import load_dotenv

from ingestion.db import get_connection, get_cursor

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = "https://api.legiscan.com/"

# LegiScan status codes -> readable names
STATUS_MAP = {
    0: "N/A",
    1: "Introduced",
    2: "Engrossed",
    3: "Enrolled",
    4: "Passed",
    5: "Vetoed",
    6: "Failed",
}


class LegiScanClient:
    """Client for the LegiScan API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["LEGISCAN_API_KEY"]
        self._request_count = 0
        self._last_request_time = 0.0

    def _request(self, op: str, **params) -> dict:
        """Make a rate-limited request to the LegiScan API."""
        # Enforce ~2 req/sec
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)

        params["key"] = self.api_key
        params["op"] = op

        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("LegiScan request failed: %s", e)
            raise

        self._last_request_time = time.time()
        self._request_count += 1

        data = resp.json()
        if data.get("status") == "ERROR":
            raise RuntimeError(f"LegiScan API error: {data.get('alert', {}).get('message', 'Unknown error')}")

        return data

    # ── Session discovery ──────────────────────────────────────────

    def get_session_list(self, state: str = "LA") -> list[dict]:
        """Get all legislative sessions for a state."""
        data = self._request("getSessionList", state=state)
        sessions = data.get("sessions", [])
        return sessions

    def get_current_session_id(self, state: str = "LA") -> int:
        """Find the most recent session ID for a state."""
        sessions = self.get_session_list(state)
        if not sessions:
            raise RuntimeError(f"No sessions found for {state}")
        # Sessions are returned newest-first; find the one where year_end >= current year
        # or just take the first (most recent)
        return sessions[0]["session_id"]

    # ── Master bill list ───────────────────────────────────────────

    def get_master_list(self, session_id: int) -> dict:
        """Get the master list of all bills in a session.

        Returns a dict mapping bill_id -> {bill_id, number, change_hash, ...}
        """
        data = self._request("getMasterList", id=session_id)
        master = data.get("masterlist", {})
        # The API wraps this oddly — the session info is under key "session"
        # and bills are under numeric keys
        bills = {}
        for key, val in master.items():
            if key == "session":
                continue
            if isinstance(val, dict) and "bill_id" in val:
                bills[val["bill_id"]] = val
        return bills

    # ── Individual bill detail ─────────────────────────────────────

    def get_bill(self, bill_id: int) -> dict:
        """Get full detail for a single bill."""
        data = self._request("getBill", id=bill_id)
        return data.get("bill", {})

    def get_bill_text(self, text_id: int) -> str | None:
        """Get and decode a bill's text. Handles both HTML and PDF formats.

        Returns decoded plain text or None.
        """
        data = self._request("getBillText", id=text_id)
        text_data = data.get("text", {})
        doc = text_data.get("doc")
        if not doc:
            return None

        try:
            raw = base64.b64decode(doc)
        except Exception as e:
            logger.warning("Failed to base64 decode bill text %d: %s", text_id, e)
            return None

        mime = text_data.get("mime", text_data.get("mime_type", ""))

        # PDF — extract text with pymupdf
        if raw[:4] == b"%PDF" or "pdf" in mime.lower():
            try:
                import fitz  # pymupdf

                pdf_doc = fitz.open(stream=raw, filetype="pdf")
                pages = []
                for page in pdf_doc:
                    pages.append(page.get_text())
                pdf_doc.close()
                text = "\n".join(pages).strip()
                if text:
                    return text
                logger.warning("PDF had no extractable text for text_id %d", text_id)
                return None
            except Exception as e:
                logger.warning("Failed to extract PDF text %d: %s", text_id, e)
                return None

        # HTML or plain text
        try:
            decoded = raw.decode("utf-8", errors="replace")
            # Strip NUL bytes that break PostgreSQL
            decoded = decoded.replace("\x00", "")
            # If it looks like HTML, strip tags for plain text storage
            if "<html" in decoded.lower() or "<body" in decoded.lower():
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(decoded, "html.parser")
                return soup.get_text(separator="\n", strip=True)
            return decoded
        except Exception as e:
            logger.warning("Failed to decode bill text %d: %s", text_id, e)
            return None

    # ── Legislator detail ──────────────────────────────────────────

    def get_person(self, people_id: int) -> dict:
        """Get legislator details including ftm_eid cross-reference."""
        data = self._request("getPerson", id=people_id)
        return data.get("person", {})

    # ── Database sync ──────────────────────────────────────────────

    def sync_session(self, session_id: int, fetch_text: bool = True) -> dict:
        """Pull all bills for a session and upsert into the database.

        Args:
            session_id: LegiScan session ID
            fetch_text: Whether to fetch full bill text (uses extra API calls)

        Returns:
            Summary dict with counts of new/updated bills and legislators
        """
        logger.info("Syncing session %d...", session_id)
        master = self.get_master_list(session_id)
        logger.info("Found %d bills in session", len(master))

        conn = get_connection()
        stats = {"bills_new": 0, "bills_updated": 0, "legislators_new": 0, "sponsors_linked": 0}

        try:
            cur = get_cursor(conn)

            for bill_id, summary in master.items():
                # Check if bill exists and if change_hash differs
                cur.execute(
                    "SELECT id, updated_at FROM bills WHERE legiscan_bill_id = %s",
                    (bill_id,),
                )
                existing = cur.fetchone()

                # Fetch full bill detail
                detail = self.get_bill(bill_id)
                if not detail:
                    logger.warning("Could not fetch bill %d", bill_id)
                    continue

                # Determine body from bill number
                bill_number = detail.get("bill_number", "")
                body = "House" if bill_number.upper().startswith("H") else "Senate"

                # Map status code
                status_code = detail.get("status", 0)
                current_status = STATUS_MAP.get(status_code, str(status_code))
                status_date = detail.get("status_date") or None

                # Fetch bill text if requested and available
                bill_text = None
                if fetch_text:
                    texts = detail.get("texts", [])
                    if texts:
                        # Get the most recent text version
                        latest_text = max(texts, key=lambda t: t.get("date", ""))
                        bill_text = self.get_bill_text(latest_text["doc_id"])

                # Upsert bill
                if existing:
                    cur.execute(
                        """UPDATE bills SET
                            title = %s, description = %s, body = %s,
                            current_status = %s, status_date = %s, url = %s,
                            bill_text = %s, updated_at = NOW()
                        WHERE legiscan_bill_id = %s""",
                        (
                            detail.get("title", ""),
                            detail.get("description", ""),
                            body,
                            current_status,
                            status_date,
                            detail.get("url", ""),
                            bill_text,
                            bill_id,
                        ),
                    )
                    stats["bills_updated"] += 1
                    db_bill_id = existing["id"]
                else:
                    cur.execute(
                        """INSERT INTO bills
                            (legiscan_bill_id, session_id, bill_number, title, description,
                             body, current_status, status_date, url, bill_text)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id""",
                        (
                            bill_id,
                            session_id,
                            bill_number,
                            detail.get("title", ""),
                            detail.get("description", ""),
                            body,
                            current_status,
                            status_date,
                            detail.get("url", ""),
                            bill_text,
                        ),
                    )
                    db_bill_id = cur.fetchone()["id"]
                    stats["bills_new"] += 1

                # Process sponsors
                sponsors = detail.get("sponsors", [])
                for sponsor in sponsors:
                    people_id = sponsor.get("people_id")
                    if not people_id:
                        continue

                    # Upsert legislator
                    cur.execute(
                        "SELECT id FROM legislators WHERE legiscan_people_id = %s",
                        (people_id,),
                    )
                    leg_row = cur.fetchone()

                    if not leg_row:
                        # Fetch full person detail for ftm_eid and other fields
                        person = self.get_person(people_id)
                        party_code = person.get("party", sponsor.get("party", ""))
                        # Map party_id to letter
                        party_map = {1: "D", 2: "R", 3: "I"}
                        if isinstance(party_code, int):
                            party_code = party_map.get(party_code, str(party_code))

                        role = sponsor.get("role", "")
                        if role == "1" or role == 1:
                            role = "Rep"
                        elif role == "2" or role == 2:
                            role = "Sen"

                        cur.execute(
                            """INSERT INTO legislators
                                (legiscan_people_id, name, first_name, last_name,
                                 party, role, district, ftm_eid, ballotpedia_url)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (legiscan_people_id) DO NOTHING
                            RETURNING id""",
                            (
                                people_id,
                                person.get("name", sponsor.get("name", "")),
                                person.get("first_name", ""),
                                person.get("last_name", ""),
                                party_code,
                                role,
                                person.get("district", sponsor.get("district", "")),
                                person.get("ftm_eid", "") or None,
                                person.get("ballotpedia", "") or None,
                            ),
                        )
                        result = cur.fetchone()
                        if result:
                            leg_id = result["id"]
                            stats["legislators_new"] += 1
                        else:
                            # Was inserted by concurrent call, fetch it
                            cur.execute(
                                "SELECT id FROM legislators WHERE legiscan_people_id = %s",
                                (people_id,),
                            )
                            leg_id = cur.fetchone()["id"]
                    else:
                        leg_id = leg_row["id"]

                    # Link sponsor to bill
                    sponsor_type = "Primary" if sponsor.get("sponsor_type_id", 0) == 1 else "Co-Sponsor"
                    cur.execute(
                        """INSERT INTO sponsorships (bill_id, legislator_id, sponsor_type)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (bill_id, legislator_id) DO NOTHING""",
                        (db_bill_id, leg_id, sponsor_type),
                    )
                    stats["sponsors_linked"] += 1

                # Commit every 50 bills to avoid huge transactions
                if (stats["bills_new"] + stats["bills_updated"]) % 50 == 0:
                    conn.commit()
                    logger.info(
                        "Progress: %d new, %d updated",
                        stats["bills_new"],
                        stats["bills_updated"],
                    )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        logger.info("Sync complete: %s", stats)
        return stats

    # ── Polling for updates ────────────────────────────────────────

    def poll_for_changes(self, session_id: int) -> list[int]:
        """Compare master list change hashes against stored data.

        Returns list of bill_ids that have changed since last sync.
        """
        master = self.get_master_list(session_id)
        changed = []

        conn = get_connection()
        try:
            cur = get_cursor(conn)
            for bill_id, info in master.items():
                cur.execute(
                    "SELECT updated_at FROM bills WHERE legiscan_bill_id = %s",
                    (bill_id,),
                )
                row = cur.fetchone()
                if not row:
                    # New bill
                    changed.append(bill_id)
                # For existing bills, we'd compare change_hash if we stored it.
                # For v0.1, we re-sync all bills on the daily poll.
        finally:
            conn.close()

        return changed


# ── CLI entrypoint ─────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Sync Louisiana bills from LegiScan")
    parser.add_argument("--session-id", type=int, help="LegiScan session ID (auto-detects if omitted)")
    parser.add_argument("--no-text", action="store_true", help="Skip fetching bill text (saves API calls)")
    parser.add_argument("--list-sessions", action="store_true", help="List available sessions and exit")
    args = parser.parse_args()

    client = LegiScanClient()

    if args.list_sessions:
        sessions = client.get_session_list("LA")
        for s in sessions[:10]:
            print(f"  ID: {s['session_id']}  |  {s['session_title']}  |  {s['year_start']}-{s['year_end']}")
    else:
        session_id = args.session_id or client.get_current_session_id("LA")
        print(f"Syncing session {session_id}...")
        stats = client.sync_session(session_id, fetch_text=not args.no_text)
        print(f"Done! {stats}")
