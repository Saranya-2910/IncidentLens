FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (curl for healthchecks, libpq for postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/pyproject.toml backend/README.md ./backend/
RUN pip install --no-cache-dir -e "./backend"

# Copy backend codebase
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
