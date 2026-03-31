# LATTICE

**AI-powered political intelligence for the Louisiana legislature.**

LATTICE reads every bill introduced in the Louisiana state legislature, decodes what each bill actually does in plain English, maps the money trail connecting bill sponsors to their campaign donors, detects model legislation copied across states, and predicts which bills will pass.

## Features

- **Bill Analysis** — 3-pass AI pipeline using Claude: extract statute references, explain in plain English, map donor connections
- **Legislator Profiles** — Campaign donors, sponsored bills, and conflict patterns
- **Model Legislation Detection** — Pattern matching against ALEC/SPN templates
- **Passage Prediction** — Logistic regression trained on historical outcomes, tracked with Brier score
- **Conflict Flags** — Automated detection of donor-legislation alignment patterns

## Tech Stack

- Python 3.12+, uv package manager
- PostgreSQL on Supabase with pgvector
- Anthropic Claude API (Haiku for bulk, Sonnet for deep analysis)
- Streamlit frontend
- scikit-learn for predictions

## Setup

```bash
# Install dependencies
uv sync

# Copy and fill in API keys
cp .env.example .env

# Run schema in Supabase SQL editor (db/schema.sql)

# Seed data
PYTHONPATH=. uv run python db/seed.py

# Run analysis
PYTHONPATH=. uv run python scripts/bulk_process.py --all

# Launch
uv run streamlit run app/app.py
```

## Data Sources

- [LegiScan](https://legiscan.com) — Bill text, sponsors, status, vote history
- [FollowTheMoney](https://followthemoney.org) — Campaign contributions (CC BY-NC-SA 3.0)
- [Louisiana Legislature](https://legis.la.gov) — Statute text

## Methodology

Every score, flag, and prediction is generated through documented, reproducible methods. See the Methodology page in the app for full details.

## License

MIT
