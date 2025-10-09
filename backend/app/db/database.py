from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Default DB into top-level backend/data/backend.db unless overridden
DB_PATH = os.environ.get(
    "FT_BACKEND_DB",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "backend.db")),
)
# Ensure parent directory exists if using default path
try:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _ensure_schema():  # pragma: no cover - startup utility
    """Lightweight auto-migration for newly added columns.
    Adds 'mode' and 'active_strategy' columns to bots table if missing.
    Safe to run repeatedly; only executes ALTER if column absent.
    """
    import sqlite3
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            # Detect existing columns
            res = conn.exec_driver_sql("PRAGMA table_info(bots)").fetchall()
            existing = {r[1] for r in res}
            alters = []
            if 'mode' not in existing:
                alters.append("ALTER TABLE bots ADD COLUMN mode VARCHAR")
            if 'active_strategy' not in existing:
                alters.append("ALTER TABLE bots ADD COLUMN active_strategy VARCHAR")
            for stmt in alters:
                try:
                    conn.exec_driver_sql(stmt)
                except Exception:
                    pass
    except sqlite3.OperationalError:
        # Table may not exist yet (first create); let metadata.create_all handle it later.
        pass


_ensure_schema()
