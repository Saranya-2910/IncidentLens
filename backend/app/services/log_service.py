"""Log ingestion and event retrieval business logic service."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.core.storage import save_batch_content
from app.models.log_batch import LogBatch
from app.models.log_event import LogEvent
from app.models.project import Project
from app.repositories.batch_repo import BatchRepository
from app.repositories.event_repo import EventRepository
from app.repositories.project_repo import ProjectRepository
from app.workers.tasks import process_log_batch

# Maximum allowable upload and payload sizes
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_INGEST_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class LogService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.batch_repo = BatchRepository(db)
        self.event_repo = EventRepository(db)

    async def _verify_project_ownership(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project:
        project = await self.project_repo.get_by_id_and_user(project_id, user_id)
        if not project:
            raise NotFoundError("Project not found")
        return project

    async def upload_log_file(
        self, user_id: uuid.UUID, project_id: uuid.UUID, file: UploadFile
    ) -> LogBatch:
        """Handle file upload, persist raw batch, and enqueue background worker task."""
        await self._verify_project_ownership(user_id, project_id)

        # Validate filename
        filename = file.filename or "upload.log"

        # Read content with size check
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise BadRequestError(
                f"File size exceeds maximum allowed limit of {MAX_UPLOAD_SIZE // (1024 * 1024)} MB"
            )

        if len(content) == 0:
            raise BadRequestError("Uploaded file is empty")

        batch_id = uuid.uuid4()
        storage_path = save_batch_content(batch_id, content)

        batch = await self.batch_repo.create(
            project_id=project_id,
            source="upload",
            filename=filename,
            storage_path=storage_path,
        )

        # Dispatch background worker task
        process_log_batch.delay(str(batch.id))
        return batch

    async def ingest_via_api(
        self, project: Project, raw_payload: str | bytes
    ) -> LogBatch:
        """Handle HTTP ingestion of log lines from X-API-Key authenticated clients."""
        payload_bytes = (
            raw_payload.encode("utf-8")
            if isinstance(raw_payload, str)
            else raw_payload
        )

        if len(payload_bytes) > MAX_INGEST_PAYLOAD_SIZE:
            raise BadRequestError(
                f"Payload size exceeds maximum allowed limit of {MAX_INGEST_PAYLOAD_SIZE // (1024 * 1024)} MB"
            )

        if len(payload_bytes) == 0:
            raise BadRequestError("Ingestion payload cannot be empty")

        batch_id = uuid.uuid4()
        storage_path = save_batch_content(batch_id, payload_bytes)

        batch = await self.batch_repo.create(
            project_id=project.id,
            source="api",
            filename="api_ingest.ndjson",
            storage_path=storage_path,
        )

        # Dispatch background worker task
        process_log_batch.delay(str(batch.id))
        return batch

    async def load_demo_data(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        scenario_id: str | None = None,
    ) -> tuple[LogBatch, str, int]:
        """Seed project with a simulated scenario dataset and queue background ingestion."""
        await self._verify_project_ownership(user_id, project_id)

        target_scenario = (
            scenario_id.strip()
            if scenario_id and scenario_id.strip()
            else "db_pool_exhaustion_low_noise_multi_service"
        )

        scenarios_dir, _ = self._resolve_simulator_paths()
        scenario_file = scenarios_dir / f"{target_scenario}.log"

        if not scenario_file.exists():
            raise BadRequestError(
                f"Demo scenario '{target_scenario}' not found. Please verify the scenario name."
            )

        content = scenario_file.read_bytes()
        if not content:
            raise BadRequestError(f"Scenario log file '{scenario_file.name}' is empty")

        total_lines = len(content.splitlines())

        batch_id = uuid.uuid4()
        storage_path = save_batch_content(batch_id, content)

        batch = await self.batch_repo.create(
            project_id=project_id,
            source="demo",
            filename=f"{target_scenario}.log",
            storage_path=storage_path,
        )

        # Dispatch background processing task
        process_log_batch.delay(str(batch.id))
        return batch, target_scenario, total_lines

    def list_demo_scenarios(self) -> list[dict[str, Any]]:
        """List all available simulated scenario datasets and their metadata."""
        _, gt_file = self._resolve_simulator_paths()
        if not gt_file.exists():
            return []
        try:
            raw_data = json.loads(gt_file.read_text(encoding="utf-8"))
            return list(raw_data.values())
        except Exception:
            return []

    @staticmethod
    def _resolve_simulator_paths() -> tuple[Path, Path]:
        """Locate simulator scenario files and ground truth manifest."""
        candidates = [
            Path("simulator"),
            Path("../simulator"),
            Path(__file__).resolve().parents[3] / "simulator",
        ]
        for c in candidates:
            scenarios = c / "scenarios"
            gt = c / "ground_truth.json"
            if scenarios.is_dir() and gt.exists():
                return scenarios, gt

        fallback = Path(__file__).resolve().parents[3] / "simulator"
        return fallback / "scenarios", fallback / "ground_truth.json"

    async def get_batch_by_id(
        self, user_id: uuid.UUID, batch_id: uuid.UUID
    ) -> LogBatch:
        """Retrieve batch ensuring the current user owns the project."""
        batch = await self.batch_repo.get_by_id(batch_id)
        if not batch:
            raise NotFoundError("Batch not found")

        # Verify user owns the project
        project = await self.project_repo.get_by_id_and_user(batch.project_id, user_id)
        if not project:
            raise NotFoundError("Batch not found")

        return batch

    async def list_batches_for_project(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LogBatch]:
        """List log batches for an owned project."""
        await self._verify_project_ownership(user_id, project_id)
        return await self.batch_repo.list_by_project(
            project_id, limit=limit, offset=offset
        )

    async def search_events(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        service: str | None = None,
        level: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        pattern_id: uuid.UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LogEvent], int]:
        """Search and filter events for an owned project."""
        await self._verify_project_ownership(user_id, project_id)
        return await self.event_repo.search_events(
            project_id=project_id,
            service=service,
            level=level,
            start_time=start_time,
            end_time=end_time,
            pattern_id=pattern_id,
            query_text=query,
            limit=limit,
            offset=offset,
        )

    async def get_event_by_id(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        event_id: int,
    ) -> LogEvent:
        """Retrieve a single stored event strictly scoped to the owned project."""
        await self._verify_project_ownership(user_id, project_id)
        event = await self.event_repo.get_by_id(project_id, event_id)
        if not event:
            raise NotFoundError("Log event not found")
        return event
