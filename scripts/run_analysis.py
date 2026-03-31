"""Run AI analysis on all bills in the current session.

Supports two modes:
1. Sequential: Analyze bills one at a time (good for testing)
2. Batch: Submit all bills to the Anthropic Batch API (50% cheaper, takes up to 24h)

Usage:
    uv run python scripts/run_analysis.py                    # Sequential, all unanalyzed bills
    uv run python scripts/run_analysis.py --batch            # Submit to Batch API
    uv run python scripts/run_analysis.py --batch-poll ID    # Check batch status
    uv run python scripts/run_analysis.py --limit 10         # Only analyze 10 bills
    uv run python scripts/run_analysis.py --deep-threshold 0.7  # Re-analyze high-controversy with Sonnet
"""

import argparse
import logging
import sys

from analysis.bill_analyzer import BillAnalyzer
from ingestion.db import get_connection, get_cursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_unanalyzed_bills(limit: int | None = None) -> list[int]:
    """Get bill IDs that have text but no analysis yet."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        query = """
            SELECT b.id FROM bills b
            LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
            WHERE b.bill_text IS NOT NULL
              AND ba.id IS NULL
            ORDER BY b.id
        """
        if limit:
            query += f" LIMIT {limit}"
        cur.execute(query)
        return [row["id"] for row in cur.fetchall()]
    finally:
        conn.close()


def get_high_controversy_bills(threshold: float = 0.7) -> list[int]:
    """Get bills with controversy score above threshold for deep re-analysis."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """SELECT bill_id FROM bill_analyses
            WHERE controversy_score >= %s AND analysis_model LIKE '%%haiku%%'
            ORDER BY controversy_score DESC""",
            (threshold,),
        )
        return [row["bill_id"] for row in cur.fetchall()]
    finally:
        conn.close()


def run_sequential(analyzer: BillAnalyzer, bill_ids: list[int], deep: bool = False):
    """Analyze bills one at a time."""
    total = len(bill_ids)
    success = 0
    skipped = 0
    errors = 0

    for i, bill_id in enumerate(bill_ids, 1):
        try:
            result = analyzer.analyze_bill(bill_id, deep=deep)
            status = result.get("status", "unknown")
            if status == "success":
                success += 1
            elif status == "skipped":
                skipped += 1
            elif status == "pending":
                skipped += 1
            else:
                errors += 1
            logger.info("[%d/%d] Bill %d: %s", i, total, bill_id, status)
        except Exception as e:
            logger.error("[%d/%d] Bill %d: ERROR — %s", i, total, bill_id, e)
            errors += 1

    print(f"\nAnalysis complete: {success} succeeded, {skipped} skipped, {errors} errors")


def run_batch(analyzer: BillAnalyzer, bill_ids: list[int]):
    """Submit bills to the Batch API."""
    print(f"Preparing batch for {len(bill_ids)} bills...")
    requests_list = analyzer.create_batch_requests(bill_ids)

    if not requests_list:
        print("No bills to process.")
        return

    print(f"Submitting {len(requests_list)} requests to Batch API...")
    batch_id = analyzer.submit_batch(requests_list)
    print(f"\nBatch submitted! ID: {batch_id}")
    print(f"Check status with: uv run python scripts/run_analysis.py --batch-poll {batch_id}")


def main():
    parser = argparse.ArgumentParser(description="Run AI analysis on bills")
    parser.add_argument("--batch", action="store_true", help="Use Batch API (50% cheaper)")
    parser.add_argument("--batch-poll", type=str, help="Poll a batch by ID")
    parser.add_argument("--limit", type=int, help="Max bills to analyze")
    parser.add_argument("--deep-threshold", type=float, help="Re-analyze controversial bills with Sonnet")
    args = parser.parse_args()

    analyzer = BillAnalyzer()

    if args.batch_poll:
        result = analyzer.poll_batch(args.batch_poll)
        print(f"Batch status: {result}")
        return

    if args.deep_threshold:
        bill_ids = get_high_controversy_bills(args.deep_threshold)
        print(f"Found {len(bill_ids)} high-controversy bills for deep analysis")
        run_sequential(analyzer, bill_ids, deep=True)
        return

    bill_ids = get_unanalyzed_bills(limit=args.limit)
    print(f"Found {len(bill_ids)} unanalyzed bills")

    if not bill_ids:
        print("Nothing to analyze. All bills with text have been processed.")
        return

    if args.batch:
        run_batch(analyzer, bill_ids)
    else:
        run_sequential(analyzer, bill_ids)


if __name__ == "__main__":
    main()
