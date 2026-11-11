"""SQLAlchemy declarative base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# Import all models so Base.metadata knows about them
import app.models  # noqa: F401, E402
