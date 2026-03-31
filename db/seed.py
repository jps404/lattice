"""Seed the database with Louisiana legislative data from LegiScan.

Usage:
    uv run python db/seed.py                    # Auto-detect current session
    uv run python db/seed.py --session-id 2084  # Specific session
    uv run python db/seed.py --no-text           # Skip bill text (faster, fewer API calls)
    uv run python db/seed.py --finance           # Also pull campaign finance data
"""

import argparse
import logging
import sys

from ingestion.legiscan import LegiScanClient
from ingestion.campaign_finance import FollowTheMoneyClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Seed LATTICE database from LegiScan")
    parser.add_argument("--session-id", type=int, help="LegiScan session ID")
    parser.add_argument("--no-text", action="store_true", help="Skip fetching full bill text")
    parser.add_argument("--finance", action="store_true", help="Also sync campaign finance data")
    parser.add_argument("--list-sessions", action="store_true", help="List sessions and exit")
    args = parser.parse_args()

    client = LegiScanClient()

    # List sessions
    if args.list_sessions:
        print("\nLouisiana Legislative Sessions:")
        print("-" * 60)
        sessions = client.get_session_list("LA")
        for s in sessions[:10]:
            print(f"  ID: {s['session_id']:>5}  |  {s['session_title']}")
        return

    # Determine session
    session_id = args.session_id
    if not session_id:
        session_id = client.get_current_session_id("LA")
        print(f"Auto-detected current session: {session_id}")

    # Sync bills and legislators
    print(f"\n{'='*60}")
    print(f"  LATTICE Data Seed — Session {session_id}")
    print(f"{'='*60}\n")

    print("Step 1: Syncing bills and legislators from LegiScan...")
    bill_stats = client.sync_session(session_id, fetch_text=not args.no_text)
    print(f"  Bills:       {bill_stats['bills_new']} new, {bill_stats['bills_updated']} updated")
    print(f"  Legislators: {bill_stats['legislators_new']} new")
    print(f"  Sponsors:    {bill_stats['sponsors_linked']} links created")

    # Optionally sync campaign finance
    if args.finance:
        print("\nStep 2: Syncing campaign finance data from FollowTheMoney...")
        ftm = FollowTheMoneyClient()
        finance_stats = ftm.sync_all_legislators()
        print(f"  Legislators processed: {finance_stats['legislators_processed']}")
        print(f"  Contributions loaded:  {finance_stats['total_contributions']}")
        print(f"  Errors:               {finance_stats['errors']}")

    print(f"\n{'='*60}")
    print("  Seed complete!")
    print(f"{'='*60}\n")
    print("API calls used this run:", client._request_count)


if __name__ == "__main__":
    main()
