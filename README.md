# IncidentLens

AI-Powered Incident Log Explainer with Evidence-Linked Root-Cause Reports.

IncidentLens turns thousands of application log lines into a short, evidence-backed incident root-cause report where every claim cites specific log lines verified by the backend.

## Tech Stack
- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Celery, Redis
- **Database**: PostgreSQL 16 + pgvector
- **AI**: Google Gemini (`google-genai`) with structured output & citation verification
- **Frontend**: React + Vite + Tailwind CSS

## Architecture
See [docs/architecture.md](docs/architecture.md) for full design details and [docs/decisions.md](docs/decisions.md) for architectural decision records.
