"""Louisiana Revised Statutes reference resolver.

Extracts R.S. citations from bill text and fetches the referenced statute
sections from the Louisiana Legislature's website.

Examples of citations this handles:
- R.S. 30:4(A)(1)
- La. R.S. 22:1892
- La. C.C. Art. 2315
- Title 22 of the Louisiana Revised Statutes
"""

import re
import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Regex patterns for Louisiana statute citations
RS_PATTERN = re.compile(
    r"R\.?\s*S\.?\s*(\d{1,2}):(\d{1,5}(?:\.\d+)?(?:\([A-Za-z0-9]+\))*)",
    re.IGNORECASE,
)

CIVIL_CODE_PATTERN = re.compile(
    r"(?:La\.?\s*)?C\.?\s*C\.?\s*(?:Art\.?\s*)?(\d{1,5})",
    re.IGNORECASE,
)

# Louisiana Legislature statute lookup base URL
STATUTE_BASE_URL = "https://legis.la.gov/legis/Law.aspx"


def extract_references(text: str) -> list[dict]:
    """Extract all statute references from bill text.

    Returns list of dicts like:
        {"citation": "R.S. 30:4(A)(1)", "title": "30", "section": "4", "type": "RS"}
    """
    refs = []
    seen = set()

    for match in RS_PATTERN.finditer(text):
        title = match.group(1)
        section = match.group(2)
        citation = f"R.S. {title}:{section}"
        if citation not in seen:
            refs.append({"citation": citation, "title": title, "section": section, "type": "RS"})
            seen.add(citation)

    for match in CIVIL_CODE_PATTERN.finditer(text):
        article = match.group(1)
        citation = f"C.C. Art. {article}"
        if citation not in seen:
            refs.append({"citation": citation, "article": article, "type": "CC"})
            seen.add(citation)

    return refs


def fetch_statute_text(title: str, section: str) -> str | None:
    """Fetch the text of a Louisiana Revised Statute section.

    Args:
        title: Title number (e.g., "30")
        section: Section number (e.g., "4")

    Returns:
        The statute text, or None if not found.
    """
    # Clean section to just the base number (strip subsection references)
    base_section = section.split("(")[0]

    try:
        resp = requests.get(
            STATUTE_BASE_URL,
            params={"d": f"{title}:{base_section}"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to fetch R.S. %s:%s — %s", title, base_section, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for the statute content — the actual selector depends on the page structure
    content_div = soup.select_one("#ContentPlaceHolder1_txtLaw") or soup.select_one(".law-text")
    if content_div:
        return content_div.get_text(separator="\n", strip=True)

    # Fallback: grab the main content area
    main = soup.select_one("main") or soup.select_one("#content")
    if main:
        return main.get_text(separator="\n", strip=True)[:5000]  # Cap at 5000 chars

    logger.warning("Could not parse statute text for R.S. %s:%s", title, base_section)
    return None


def resolve_references(bill_text: str, max_refs: int = 10) -> dict:
    """Extract references from bill text and fetch their statute text.

    Args:
        bill_text: The full text of a bill
        max_refs: Maximum number of statutes to fetch (to limit API calls)

    Returns:
        Dict with "references" list and "statute_texts" dict mapping citation -> text
    """
    refs = extract_references(bill_text)
    logger.info("Found %d statute references in bill text", len(refs))

    statute_texts = {}
    for ref in refs[:max_refs]:
        if ref["type"] == "RS":
            text = fetch_statute_text(ref["title"], ref["section"])
            if text:
                statute_texts[ref["citation"]] = text

    return {"references": refs, "statute_texts": statute_texts}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Test with a sample citation
    sample = "This bill amends R.S. 30:4(A)(1) and R.S. 22:1892 to require..."
    result = resolve_references(sample)
    print(f"References found: {len(result['references'])}")
    for ref in result["references"]:
        print(f"  {ref['citation']}")
    print(f"Statute texts fetched: {len(result['statute_texts'])}")
