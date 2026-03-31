"""Bulk process: fetch all bill text, then analyze everything.

Usage:
    PYTHONPATH=. uv run python scripts/bulk_process.py --fetch-text
    PYTHONPATH=. uv run python scripts/bulk_process.py --analyze
    PYTHONPATH=. uv run python scripts/bulk_process.py --all
"""

import argparse
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def fetch_all_text():
    """Fetch bill text for every bill that doesn't have it yet."""
    from ingestion.legiscan import LegiScanClient
    from ingestion.db import get_connection, get_cursor

    client = LegiScanClient()
    conn = get_connection()
    cur = get_cursor(conn)

    cur.execute("SELECT id, legiscan_bill_id, bill_number FROM bills WHERE bill_text IS NULL ORDER BY id")
    bills = cur.fetchall()
    total = len(bills)
    logger.info("Fetching text for %d bills...", total)

    updated = 0
    skipped = 0
    errors = 0

    for i, bill in enumerate(bills, 1):
        try:
            detail = client.get_bill(bill["legiscan_bill_id"])
            texts = detail.get("texts", [])
            if texts:
                latest = max(texts, key=lambda t: t.get("date", ""))
                text = client.get_bill_text(latest["doc_id"])
                if text:
                    cur.execute("UPDATE bills SET bill_text = %s WHERE id = %s", (text, bill["id"]))
                    updated += 1
                else:
                    skipped += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            if "rate" in str(e).lower():
                time.sleep(5)

        if i % 25 == 0:
            conn.commit()
            logger.info("  [%d/%d] %d fetched, %d skipped, %d errors", i, total, updated, skipped, errors)

    conn.commit()
    conn.close()
    logger.info("Text fetch complete: %d fetched, %d skipped, %d errors", updated, skipped, errors)
    return updated


def analyze_all():
    """Run AI analysis on every bill that has text but no analysis."""
    from analysis.bill_analyzer import BillAnalyzer
    from ingestion.db import get_connection, get_cursor

    analyzer = BillAnalyzer()
    conn = get_connection()
    cur = get_cursor(conn)

    cur.execute("""
        SELECT b.id, b.bill_number, LENGTH(b.bill_text) as text_len
        FROM bills b
        LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
        WHERE b.bill_text IS NOT NULL AND ba.id IS NULL
        ORDER BY LENGTH(b.bill_text) ASC
    """)
    bills = cur.fetchall()
    conn.close()

    total = len(bills)
    logger.info("Analyzing %d bills...", total)

    success = 0
    errors = 0

    for i, bill in enumerate(bills, 1):
        try:
            result = analyzer.analyze_bill(bill["id"])
            status = result.get("status", "unknown")
            if status == "success":
                success += 1
            elif status == "error":
                errors += 1
        except Exception as e:
            errors += 1
            logger.warning("  %s: %s", bill["bill_number"], e)
            if "rate" in str(e).lower() or "429" in str(e):
                time.sleep(10)

        if i % 10 == 0:
            logger.info("  [%d/%d] %d analyzed, %d errors", i, total, success, errors)

    logger.info("Analysis complete: %d/%d succeeded, %d errors", success, total, errors)
    return success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-text", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all or args.fetch_text:
        fetch_all_text()

    if args.all or args.analyze:
        analyze_all()

    if not (args.all or args.fetch_text or args.analyze):
        parser.print_help()


if __name__ == "__main__":
    main()
