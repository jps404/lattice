"""Bill similarity search using pgvector cosine similarity.

Finds bills similar to a given bill or arbitrary text using the
embeddings stored in bill_embeddings.
"""

import json
import logging
import os

import openai
from dotenv import load_dotenv

from ingestion.db import get_connection, get_cursor

load_dotenv()
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"


def find_similar_bills(bill_id: int, limit: int = 10, min_score: float = 0.3) -> list[dict]:
    """Find bills most similar to a given bill using cosine similarity.

    Args:
        bill_id: The reference bill's database ID
        limit: Max number of similar bills to return
        min_score: Minimum similarity score (0-1) to include

    Returns:
        List of dicts with bill info and similarity_score, sorted by similarity desc.
    """
    conn = get_connection()
    try:
        cur = get_cursor(conn)

        # Get the reference bill's embedding
        cur.execute("SELECT embedding FROM bill_embeddings WHERE bill_id = %s", (bill_id,))
        row = cur.fetchone()
        if not row:
            logger.warning("No embedding found for bill %d", bill_id)
            return []

        # Use pgvector cosine distance operator (<=>)
        # cosine_distance = 1 - cosine_similarity, so we compute 1 - distance
        cur.execute(
            """
            SELECT b.id, b.bill_number, b.title, b.current_status,
                   ba.plain_english, ba.policy_area,
                   1 - (be.embedding <=> (SELECT embedding FROM bill_embeddings WHERE bill_id = %s)) as similarity_score
            FROM bill_embeddings be
            JOIN bills b ON b.id = be.bill_id
            LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
            WHERE be.bill_id != %s
            ORDER BY be.embedding <=> (SELECT embedding FROM bill_embeddings WHERE bill_id = %s)
            LIMIT %s
            """,
            (bill_id, bill_id, bill_id, limit),
        )

        results = []
        for row in cur.fetchall():
            score = float(row["similarity_score"])
            if score >= min_score:
                results.append(dict(row))

        return results
    finally:
        conn.close()


def search_by_text(query: str, limit: int = 10, min_score: float = 0.3) -> list[dict]:
    """Search for bills similar to arbitrary text.

    Generates an embedding for the query text and searches against stored embeddings.

    Args:
        query: Natural language search query
        limit: Max results
        min_score: Minimum similarity threshold

    Returns:
        List of matching bills with similarity scores.
    """
    # Generate embedding for query
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    query_embedding = response.data[0].embedding
    embedding_str = json.dumps(query_embedding)

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT b.id, b.bill_number, b.title, b.current_status,
                   ba.plain_english, ba.policy_area,
                   1 - (be.embedding <=> %s::vector) as similarity_score
            FROM bill_embeddings be
            JOIN bills b ON b.id = be.bill_id
            LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
            ORDER BY be.embedding <=> %s::vector
            LIMIT %s
            """,
            (embedding_str, embedding_str, limit),
        )

        results = []
        for row in cur.fetchall():
            score = float(row["similarity_score"])
            if score >= min_score:
                results.append(dict(row))

        return results
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--bill-id", type=int, help="Find bills similar to this bill")
    parser.add_argument("--query", type=str, help="Search by text")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.bill_id:
        results = find_similar_bills(args.bill_id, limit=args.limit)
    elif args.query:
        results = search_by_text(args.query, limit=args.limit)
    else:
        print("Provide --bill-id or --query")
        exit(1)

    for r in results:
        print(f"  {r['bill_number']:>10}  [{r.get('similarity_score', 0):.3f}]  {r['title'][:70]}")
