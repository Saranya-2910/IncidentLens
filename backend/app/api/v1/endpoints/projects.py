"""Project management endpoints scoped strictly to the authenticated user."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project owned by current user",
)
async def create_project(
    data: ProjectCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    project_service = ProjectService(db)
    project = await project_service.create_project(current_user.id, data)
    return ProjectResponse.model_validate(project)


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List all projects owned by current user",
)
async def list_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProjectResponse]:
    project_service = ProjectService(db)
    projects = await project_service.list_projects(current_user.id)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get(
    "/{id}",
    response_model=ProjectResponse,
    summary="Get details of a specific project",
)
async def get_project(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    project_service = ProjectService(db)
    project = await project_service.get_project(current_user.id, id)
    return ProjectResponse.model_validate(project)


@router.patch(
    "/{id}",
    response_model=ProjectResponse,
    summary="Update an owned project",
)
async def update_project(
    id: uuid.UUID,
    data: ProjectUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    project_service = ProjectService(db)
    project = await project_service.update_project(current_user.id, id, data)
    return ProjectResponse.model_validate(project)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an owned project",
)
async def delete_project(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    project_service = ProjectService(db)
    await project_service.delete_project(current_user.id, id)
