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

## Evaluation & Benchmarks

Measured end-to-end (`ingest -> parse -> normalise -> group -> detect -> explain & verify`) across **34 simulated scenarios** (32 incident variants across 8 root-cause categories + 2 control datasets, totaling **22,416 raw log lines**), reproduced via `python eval/run_eval.py --mode offline`:

| Metric | IncidentLens Pipeline | Naive Tail Baseline (Last 100 Lines) |
| :--- | :--- | :--- |
| **Incident Detection Recall** | **100.0%** (32/32) | N/A (no detector) |
| **Control Dataset False Alarms** | **0/2** (0% false positives) | 2/2 |
| **Origin Pattern Accuracy (Top-1 / Top-3)** | **100.0% / 100.0%** | N/A |
| **Root-Cause Category Accuracy** | **100.0%** | 46.9% |
| **Origin Service Accuracy** | **93.8%** (30/32) | 62.5% |
| **Citation Validity Rate** | **100.0%** (DB-verified IDs) | 0.0% (no verification) |
| **Unsupported Claim Rate** | **0.0%** | 100.0% (unverified) |
| **Log Reduction Ratio (Raw -> LLM)** | **98.42%** (354 / 22,416 lines) | 84.85% (3,395 / 22,416 lines) |
| **Avg Tokens per Report** | **1,003.1 tokens** | 3,838.1 tokens (~3.8x higher) |

See [eval/results.md](eval/results.md) for per-scenario results and failure analysis.
