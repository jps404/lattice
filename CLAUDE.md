# LATTICE — AI-Powered Political Intelligence Platform

## Project overview
Louisiana prototype of a state legislature transparency tool. Reads bills, decodes them in plain English, maps money trails, detects model legislation, and predicts passage.

## Tech stack
- Python 3.12+, uv package manager
- PostgreSQL on Supabase (free tier) with pgvector
- Claude API (Haiku for bulk, Sonnet for deep analysis)
- OpenAI text-embedding-3-small for embeddings
- Streamlit frontend, scikit-learn for predictions
- GitHub Actions for daily polling

## Key commands
- `uv run streamlit run app/app.py` — launch the frontend
- `uv run python scripts/run_analysis.py` — analyze all bills
- `uv run python scripts/generate_embeddings.py` — generate embeddings
- `uv run python scripts/train_predictor.py` — train prediction model

## Political neutrality
Never editorialize or take political positions. Frame conflict flags as "patterns detected" not "corruption found." Always link to original sources.
