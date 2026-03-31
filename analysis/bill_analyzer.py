"""3-pass AI bill analysis pipeline.

Pass 1: Extract statute references from bill text
Pass 2: Plain-English analysis with statute context
Pass 3: Money trail connection (run after campaign finance data loaded)

Uses Claude Haiku for bulk analysis, Sonnet for deep dives on flagged bills.
Supports Batch API for processing entire sessions at 50% discount.
"""

import json
import logging
import os
import time

import anthropic
from dotenv import load_dotenv

from ingestion.db import get_connection, get_cursor
from ingestion.statutes import resolve_references

load_dotenv()
logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20250514"

# Max bill text length before chunking (~80K tokens ≈ 320K chars)
MAX_TEXT_LENGTH = 300_000


class BillAnalyzer:
    """Runs the 3-pass analysis pipeline on bills."""

    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def _call_claude(self, system: str, user: str, model: str = HAIKU_MODEL) -> str:
        """Make a single Claude API call with retry logic."""
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                wait = 2 ** attempt * 5
                logger.warning("Rate limited, waiting %ds...", wait)
                time.sleep(wait)
            except anthropic.APIError as e:
                logger.error("Claude API error (attempt %d): %s", attempt + 1, e)
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def _parse_json_response(self, text: str) -> dict:
        """Extract JSON from a Claude response, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            # Strip markdown code fences
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse JSON from response: %s...", text[:200])
            return {}

    # ── Pass 1: Reference identification ───────────────────────────

    def pass1_extract_references(self, bill_text: str) -> list[str]:
        """Extract statute references using regex + AI validation."""
        # Start with regex extraction (fast, free)
        result = resolve_references(bill_text, max_refs=0)  # Don't fetch yet
        regex_refs = [r["citation"] for r in result["references"]]

        # If bill is short enough, also use AI to catch references regex misses
        if len(bill_text) < 50_000:
            system = (
                "You are a legislative analyst. Given the text of a bill, identify all "
                "references to existing law (e.g., 'R.S. 30:4(A)(1)', 'La. C.C. Art. 2315', "
                "'Title 22 of the Louisiana Revised Statutes'). Return a JSON object with a "
                "'references' array of citation strings. Only return the JSON, nothing else."
            )
            response = self._call_claude(system, bill_text[:50_000])
            if response:
                parsed = self._parse_json_response(response)
                ai_refs = parsed.get("references", [])
                # Merge, dedup
                all_refs = list(dict.fromkeys(regex_refs + ai_refs))
                return all_refs

        return regex_refs

    # ── Pass 2: Plain-English analysis ─────────────────────────────

    def pass2_analyze(self, bill_text: str, statute_context: str, model: str = HAIKU_MODEL) -> dict:
        """Generate plain-English analysis of a bill with statute context."""
        system = (
            "You are a senior legislative analyst who explains bills to non-lawyers. "
            "You have been given a bill AND the text of all existing laws it references.\n\n"
            "Your job: Explain what this bill ACTUALLY DOES — not what the title says, not what "
            "the press release claims. Focus on:\n"
            "1. What specific changes does it make to existing law?\n"
            "2. What NEW powers, restrictions, or obligations does it create?\n"
            "3. What existing protections or requirements does it REMOVE?\n"
            "4. Are there any carve-outs, exemptions, or loopholes buried in the text?\n\n"
            "Write in plain English. No legal jargon. Be specific about what changes.\n\n"
            "Return ONLY a JSON object with these fields:\n"
            '- "plain_english": 2-4 sentence summary of what this bill actually does\n'
            '- "key_changes": array of specific changes\n'
            '- "who_benefits": who gains from this bill\n'
            '- "who_is_harmed": who loses from this bill\n'
            '- "hidden_provisions": any buried loopholes or carve-outs\n'
            '- "policy_area": one of: healthcare, education, energy, environment, '
            "criminal_justice, taxation, housing, labor, technology, transportation, "
            "agriculture, other\n"
            '- "controversy_score": float 0.0-1.0'
        )

        # Truncate bill text if needed
        truncated_text = bill_text[:MAX_TEXT_LENGTH]

        user_msg = (
            f"<bill_text>\n{truncated_text}\n</bill_text>\n\n"
            f"<referenced_statutes>\n{statute_context}\n</referenced_statutes>"
        )

        response = self._call_claude(system, user_msg, model=model)
        if not response:
            return {}

        return self._parse_json_response(response)

    # ── Pass 3: Money trail connection ─────────────────────────────

    def pass3_money_trail(
        self,
        plain_english: str,
        policy_area: str,
        sponsor_name: str,
        sponsor_party: str,
        sponsor_district: str,
        top_donors: list[dict],
        who_benefits: str,
    ) -> dict:
        """Analyze connections between campaign donors and bill content."""
        system = (
            "You are an investigative analyst looking for connections between campaign "
            "donations and legislation. You have been given:\n"
            "1. A bill summary and its policy area\n"
            "2. The bill sponsor's top campaign donors by industry\n"
            "3. The industries that would benefit from this bill\n\n"
            "Analyze whether there is a pattern suggesting the bill was influenced by "
            "donor interests. Be factual and evidence-based. Do NOT make accusations — "
            "identify patterns and let readers draw conclusions.\n\n"
            "Return ONLY a JSON object with these fields:\n"
            '- "donor_alignment_score": float 0.0-1.0\n'
            '- "aligned_donors": array of objects with name, amount, industry, connection\n'
            '- "conflict_flags": array of description strings\n'
            '- "assessment": 1-2 sentence factual summary of the money-to-legislation connection'
        )

        donors_json = json.dumps(top_donors[:30], indent=2, default=str)

        user_msg = (
            f"<bill_summary>{plain_english}</bill_summary>\n"
            f"<policy_area>{policy_area}</policy_area>\n"
            f"<sponsor>{sponsor_name}, {sponsor_party}, District {sponsor_district}</sponsor>\n"
            f"<top_donors>\n{donors_json}\n</top_donors>\n"
            f"<bill_beneficiaries>{who_benefits}</bill_beneficiaries>"
        )

        response = self._call_claude(system, user_msg, model=HAIKU_MODEL)
        if not response:
            return {}

        return self._parse_json_response(response)

    # ── Full pipeline ──────────────────────────────────────────────

    def analyze_bill(self, bill_id: int, deep: bool = False) -> dict:
        """Run the full analysis pipeline on a single bill.

        Args:
            bill_id: Database bill ID
            deep: If True, use Sonnet instead of Haiku for Pass 2

        Returns:
            Analysis results dict
        """
        conn = get_connection()
        try:
            cur = get_cursor(conn)

            # Fetch bill
            cur.execute("SELECT * FROM bills WHERE id = %s", (bill_id,))
            bill = cur.fetchone()
            if not bill:
                raise ValueError(f"Bill {bill_id} not found")

            if not bill["bill_text"]:
                logger.warning("Bill %s has no text — skipping analysis", bill["bill_number"])
                return {"status": "pending", "reason": "no_text"}

            # Check if already analyzed
            cur.execute("SELECT id FROM bill_analyses WHERE bill_id = %s", (bill_id,))
            if cur.fetchone():
                logger.info("Bill %s already analyzed — skipping", bill["bill_number"])
                return {"status": "skipped", "reason": "already_analyzed"}

            logger.info("Analyzing bill %s: %s", bill["bill_number"], bill["title"][:60])

            # Pass 1: Extract references
            references = self.pass1_extract_references(bill["bill_text"])
            logger.info("  Pass 1: Found %d references", len(references))

            # Fetch statute context for Pass 2
            statute_result = resolve_references(bill["bill_text"], max_refs=10)
            statute_context = "\n\n".join(
                f"=== {cite} ===\n{text}"
                for cite, text in statute_result["statute_texts"].items()
            )

            # Pass 2: Plain-English analysis
            model = SONNET_MODEL if deep else HAIKU_MODEL
            analysis = self.pass2_analyze(bill["bill_text"], statute_context, model=model)
            if not analysis:
                logger.error("  Pass 2 failed for bill %s", bill["bill_number"])
                return {"status": "error", "reason": "analysis_failed"}

            logger.info("  Pass 2: Complete (policy_area=%s)", analysis.get("policy_area"))

            # Store results
            cur.execute(
                """INSERT INTO bill_analyses
                    (bill_id, plain_english, key_changes, who_benefits, who_is_harmed,
                     referenced_statutes, statute_context, policy_area,
                     controversy_score, analysis_model)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bill_id) DO UPDATE SET
                    plain_english = EXCLUDED.plain_english,
                    key_changes = EXCLUDED.key_changes,
                    who_benefits = EXCLUDED.who_benefits,
                    who_is_harmed = EXCLUDED.who_is_harmed,
                    referenced_statutes = EXCLUDED.referenced_statutes,
                    statute_context = EXCLUDED.statute_context,
                    policy_area = EXCLUDED.policy_area,
                    controversy_score = EXCLUDED.controversy_score,
                    analysis_model = EXCLUDED.analysis_model,
                    analyzed_at = NOW()""",
                (
                    bill_id,
                    analysis.get("plain_english", ""),
                    json.dumps(analysis.get("key_changes", [])),
                    analysis.get("who_benefits", ""),
                    analysis.get("who_is_harmed", ""),
                    json.dumps([r["citation"] if isinstance(r, dict) else r for r in references]),
                    statute_context[:10000],  # Cap stored context
                    analysis.get("policy_area", "other"),
                    analysis.get("controversy_score", 0.0),
                    model,
                ),
            )
            conn.commit()

            return {"status": "success", "analysis": analysis}

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Batch API support ──────────────────────────────────────────

    def create_batch_requests(self, bill_ids: list[int]) -> list[dict]:
        """Create Batch API request objects for a list of bills.

        Returns list of request dicts ready for the Batch API.
        Does NOT submit the batch — call submit_batch() with the result.
        """
        conn = get_connection()
        requests_list = []

        try:
            cur = get_cursor(conn)

            for bill_id in bill_ids:
                cur.execute("SELECT * FROM bills WHERE id = %s", (bill_id,))
                bill = cur.fetchone()
                if not bill or not bill["bill_text"]:
                    continue

                # Skip already analyzed
                cur.execute("SELECT id FROM bill_analyses WHERE bill_id = %s", (bill_id,))
                if cur.fetchone():
                    continue

                bill_text = bill["bill_text"][:MAX_TEXT_LENGTH]

                # Fetch statute context
                statute_result = resolve_references(bill["bill_text"], max_refs=5)
                statute_context = "\n\n".join(
                    f"=== {cite} ===\n{text}"
                    for cite, text in statute_result["statute_texts"].items()
                )

                system = (
                    "You are a senior legislative analyst who explains bills to non-lawyers. "
                    "Explain what this bill ACTUALLY DOES. Return ONLY a JSON object with: "
                    "plain_english, key_changes (array), who_benefits, who_is_harmed, "
                    "hidden_provisions, policy_area (healthcare/education/energy/environment/"
                    "criminal_justice/taxation/housing/labor/technology/transportation/"
                    "agriculture/other), controversy_score (0.0-1.0)."
                )

                user_msg = (
                    f"<bill_text>\n{bill_text}\n</bill_text>\n\n"
                    f"<referenced_statutes>\n{statute_context}\n</referenced_statutes>"
                )

                requests_list.append({
                    "custom_id": f"bill-{bill_id}",
                    "params": {
                        "model": HAIKU_MODEL,
                        "max_tokens": 4096,
                        "system": system,
                        "messages": [{"role": "user", "content": user_msg}],
                    },
                })
        finally:
            conn.close()

        logger.info("Created %d batch requests", len(requests_list))
        return requests_list

    def submit_batch(self, requests_list: list[dict]) -> str:
        """Submit a batch of analysis requests to the Anthropic Batch API.

        Returns the batch ID for polling.
        """
        batch = self.client.batches.create(requests=requests_list)
        logger.info("Submitted batch %s with %d requests", batch.id, len(requests_list))
        return batch.id

    def poll_batch(self, batch_id: str) -> dict:
        """Check batch status and process results if complete."""
        batch = self.client.batches.retrieve(batch_id)

        if batch.processing_status != "ended":
            logger.info("Batch %s status: %s", batch_id, batch.processing_status)
            return {"status": batch.processing_status}

        # Process results
        conn = get_connection()
        processed = 0
        errors = 0

        try:
            cur = get_cursor(conn)

            for result in self.client.batches.results(batch_id):
                custom_id = result.custom_id
                bill_id = int(custom_id.split("-")[1])

                if result.result.type == "succeeded":
                    text = result.result.message.content[0].text
                    analysis = self._parse_json_response(text)

                    if analysis:
                        # Extract references via regex for this bill
                        cur.execute("SELECT bill_text FROM bills WHERE id = %s", (bill_id,))
                        bill = cur.fetchone()
                        references = []
                        if bill and bill["bill_text"]:
                            refs = resolve_references(bill["bill_text"], max_refs=0)
                            references = [r["citation"] for r in refs["references"]]

                        cur.execute(
                            """INSERT INTO bill_analyses
                                (bill_id, plain_english, key_changes, who_benefits,
                                 who_is_harmed, referenced_statutes, policy_area,
                                 controversy_score, analysis_model)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (bill_id) DO UPDATE SET
                                plain_english = EXCLUDED.plain_english,
                                key_changes = EXCLUDED.key_changes,
                                who_benefits = EXCLUDED.who_benefits,
                                who_is_harmed = EXCLUDED.who_is_harmed,
                                referenced_statutes = EXCLUDED.referenced_statutes,
                                policy_area = EXCLUDED.policy_area,
                                controversy_score = EXCLUDED.controversy_score,
                                analysis_model = EXCLUDED.analysis_model,
                                analyzed_at = NOW()""",
                            (
                                bill_id,
                                analysis.get("plain_english", ""),
                                json.dumps(analysis.get("key_changes", [])),
                                analysis.get("who_benefits", ""),
                                analysis.get("who_is_harmed", ""),
                                json.dumps(references),
                                analysis.get("policy_area", "other"),
                                analysis.get("controversy_score", 0.0),
                                HAIKU_MODEL,
                            ),
                        )
                        processed += 1
                else:
                    logger.warning("Batch result error for bill %d: %s", bill_id, result.result.type)
                    errors += 1

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {"status": "complete", "processed": processed, "errors": errors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import argparse

    parser = argparse.ArgumentParser(description="Analyze a single bill")
    parser.add_argument("bill_id", type=int, help="Database bill ID to analyze")
    parser.add_argument("--deep", action="store_true", help="Use Sonnet for deeper analysis")
    args = parser.parse_args()

    analyzer = BillAnalyzer()
    result = analyzer.analyze_bill(args.bill_id, deep=args.deep)
    print(json.dumps(result, indent=2, default=str))
