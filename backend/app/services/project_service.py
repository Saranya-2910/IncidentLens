"""Project business logic service ensuring tenant isolation."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.project import Project
from app.repositories.project_repo import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)

    async def list_projects(self, user_id: uuid.UUID) -> list[Project]:
        return await self.project_repo.list_by_user(user_id)

    async def get_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        project = await self.project_repo.get_by_id_and_user(project_id, user_id)
        if not project:
            # Return 404 to avoid leaking existence of another user's project
            raise NotFoundError("Project not found")
        return project

    async def create_project(self, user_id: uuid.UUID, data: ProjectCreate) -> Project:
        return await self.project_repo.create(
            user_id=user_id,
            name=data.name,
            description=data.description,
        )

    async def update_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, data: ProjectUpdate
    ) -> Project:
        project = await self.get_project(user_id, project_id)
        return await self.project_repo.update(
            project=project,
            name=data.name,
            description=data.description,
        )

    async def delete_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        project = await self.get_project(user_id, project_id)
        await self.project_repo.delete(project)
