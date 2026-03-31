"""Generate and store embeddings for all bills using OpenAI text-embedding-3-small.

Embeddings are stored in the bill_embeddings table (pgvector) for similarity search.
Processes in batches of up to 2048 texts per API call.

Usage:
    uv run python scripts/generate_embeddings.py             # All bills without embeddings
    uv run python scripts/generate_embeddings.py --limit 100  # Only first 100
    uv run python scripts/generate_embeddings.py --regenerate  # Redo all
"""

import argparse
import json
import logging
import os

import openai
from dotenv import load_dotenv

from ingestion.db import get_connection, get_cursor

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BATCH_SIZE = 256  # Conservative batch size to stay within token limits


def get_bills_needing_embeddings(limit: int | None = None, regenerate: bool = False) -> list[dict]:
    """Fetch bills that need embeddings generated."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        if regenerate:
            query = """
                SELECT b.id, b.bill_number, b.title, b.description, b.bill_text,
                       ba.plain_english, ba.policy_area
                FROM bills b
                LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
                WHERE b.bill_text IS NOT NULL
                ORDER BY b.id
            """
        else:
            query = """
                SELECT b.id, b.bill_number, b.title, b.description, b.bill_text,
                       ba.plain_english, ba.policy_area
                FROM bills b
                LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
                LEFT JOIN bill_embeddings be ON be.bill_id = b.id
                WHERE b.bill_text IS NOT NULL AND be.id IS NULL
                ORDER BY b.id
            """
        if limit:
            query += f" LIMIT {limit}"
        cur.execute(query)
        return cur.fetchall()
    finally:
        conn.close()


def create_embedding_text(bill: dict) -> str:
    """Create the text to embed for a bill.

    Uses the AI analysis summary if available, otherwise falls back to
    title + description + truncated bill text. This gives better semantic
    embeddings because the plain English summary captures meaning better
    than raw legislative text.
    """
    parts = []

    if bill.get("plain_english"):
        parts.append(bill["plain_english"])

    parts.append(f"Bill: {bill['bill_number']} — {bill['title']}")

    if bill.get("description"):
        parts.append(bill["description"])

    if bill.get("policy_area"):
        parts.append(f"Policy area: {bill['policy_area']}")

    # Add truncated bill text for additional context
    if bill.get("bill_text"):
        # ~6000 chars ≈ ~1500 tokens, safe within embedding model limits
        parts.append(bill["bill_text"][:6000])

    return "\n\n".join(parts)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts."""
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )

    return [item.embedding for item in response.data]


def store_embeddings(bill_ids: list[int], embeddings: list[list[float]]):
    """Upsert embeddings into the database."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        for bill_id, embedding in zip(bill_ids, embeddings):
            embedding_str = json.dumps(embedding)
            cur.execute(
                """INSERT INTO bill_embeddings (bill_id, embedding)
                VALUES (%s, %s::vector)
                ON CONFLICT (bill_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    created_at = NOW()""",
                (bill_id, embedding_str),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Generate bill embeddings")
    parser.add_argument("--limit", type=int, help="Max bills to process")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate all embeddings")
    args = parser.parse_args()

    bills = get_bills_needing_embeddings(limit=args.limit, regenerate=args.regenerate)
    print(f"Found {len(bills)} bills needing embeddings")

    if not bills:
        print("Nothing to embed.")
        return

    total_embedded = 0

    # Process in batches
    for i in range(0, len(bills), BATCH_SIZE):
        batch = bills[i : i + BATCH_SIZE]
        texts = [create_embedding_text(b) for b in batch]
        bill_ids = [b["id"] for b in batch]

        logger.info("Generating embeddings for batch %d-%d...", i + 1, i + len(batch))

        try:
            embeddings = generate_embeddings(texts)
            store_embeddings(bill_ids, embeddings)
            total_embedded += len(embeddings)
            logger.info("Stored %d embeddings (total: %d/%d)", len(embeddings), total_embedded, len(bills))
        except Exception as e:
            logger.error("Batch failed: %s", e)
            # Continue with next batch
            continue

    print(f"\nDone! Embedded {total_embedded}/{len(bills)} bills")


if __name__ == "__main__":
    main()
