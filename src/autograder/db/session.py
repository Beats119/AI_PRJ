"""Engine/session factory. One SQLite file under the app data dir."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autograder.db.models import Base

SCHEMA_VERSION = 1


def default_data_dir() -> Path:
    base = os.environ.get("AUTOGRADER_DATA_DIR")
    return Path(base) if base else Path.cwd() / ".autograder-data"


def make_engine(db_url: str | None = None, data_dir: Path | None = None):
    if db_url is None:
        data_dir = data_dir or default_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{data_dir / 'autograder.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
