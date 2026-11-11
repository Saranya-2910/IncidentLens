"""HTTP log line ingestion endpoint using X-API-Key."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_api_key_project
from app.db.session import get_db
from app.models.project import Project
from app.schemas.log_batch import BatchUploadResponse
from app.services.log_service import LogService

router = APIRouter(tags=["Logs & Ingestion"])


@router.post(
    "/ingest",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="HTTP ingestion of log lines (JSON array, NDJSON, or text lines)",
)
async def ingest_logs(
    request: Request,
    project: Annotated[Project, Depends(get_api_key_project)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchUploadResponse:
    raw_body = await request.body()
    decoded = raw_body.decode("utf-8", errors="replace")

    # If incoming payload is a JSON array, serialize each element as NDJSON line
    stripped = decoded.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            arr = json.loads(stripped)
            if isinstance(arr, list):
                decoded = "\n".join(json.dumps(item) for item in arr)
        except Exception:
            pass

    log_service = LogService(db)
    batch = await log_service.ingest_via_api(project, decoded)
    return BatchUploadResponse(
        batch_id=batch.id,
        status=batch.status,
    )
