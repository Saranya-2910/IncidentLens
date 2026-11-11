"""Project repository ensuring all queries are strictly scoped to the owner user."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id_and_user(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> Project | None:
        """Fetch project strictly checking both project ID and owner user ID."""
        stmt = select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Project]:
        """List all projects belonging to the specified user."""
        stmt = (
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, user_id: uuid.UUID, name: str, description: str | None = None
    ) -> Project:
        """Create a new project owned by user_id."""
        project = Project(user_id=user_id, name=name, description=description)
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def update(
        self, project: Project, name: str | None = None, description: str | None = None
    ) -> Project:
        """Update an existing owned project."""
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def delete(self, project: Project) -> None:
        """Delete an owned project (cascades related entities)."""
        await self.db.delete(project)
        await self.db.commit()
