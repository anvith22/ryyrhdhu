"""Data storage module for SQLite snapshots of Elexon actuals and forecasts.

Recommendation: SQLite is recommended over Parquet because it provides zero-dependency
storage in Python's standard library and enables indexed relational queries
(filtering latest forecast before a cutoff timestamp) which the FastAPI backend requires.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def resolve_db_path(custom_path: Path | str | None = None) -> Path:
    """Resolve SQLite database path across local dev, Docker container, and Vercel serverless."""
    if custom_path is not None:
        return Path(custom_path).resolve()

    # 1. Environment variable override
    env_path = os.environ.get("DB_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path).resolve()

    # 2. Path relative to storage.py (parents[3] is repository root)
    rel_file = (Path(__file__).resolve().parents[3] / "data" / "wind_energy.db").resolve()
    if rel_file.exists():
        return rel_file

    # 3. Path relative to current working directory (Vercel runtime root /var/task)
    cwd_path = (Path.cwd() / "data" / "wind_energy.db").resolve()
    if cwd_path.exists():
        return cwd_path

    # Fallback default
    return rel_file


DEFAULT_DB_PATH = resolve_db_path()


def get_sqlite_connection(
    db_path: Path | str = DEFAULT_DB_PATH,
    read_only: bool = True,
) -> sqlite3.Connection:
    """Open or create a SQLite database connection with row access and performance pragmas.

    When read_only is True, opens using SQLite URI mode=ro so that it operates safely
    even on read-only container filesystems.
    """
    path = resolve_db_path(db_path)
    if read_only and not path.exists():
        raise FileNotFoundError(
            f"SQLite database file not found at '{path}'. "
            f"Searched: file_rel='{Path(__file__).resolve().parents[3] / 'data' / 'wind_energy.db'}', "
            f"cwd_rel='{Path.cwd() / 'data' / 'wind_energy.db'}'"
        )

    if read_only:
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.execute("PRAGMA synchronous = NORMAL;")

    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite database tables and indexes for actuals and forecasts."""
    conn = get_sqlite_connection(db_path, read_only=False)
    with conn:
        # 1. Actuals table: one unique record per 30-min settlement interval (startTime in UTC)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS actuals_wind (
                start_time TEXT PRIMARY KEY,
                generation_mw REAL NOT NULL,
                settlement_date TEXT NOT NULL,
                settlement_period INTEGER NOT NULL
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_actuals_settlement_date
            ON actuals_wind (settlement_date);
        """)

        # 2. Forecasts table: multiple forecast publications per target startTime
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forecasts_wind (
                start_time TEXT NOT NULL,
                publish_time TEXT NOT NULL,
                generation_mw REAL NOT NULL,
                horizon_hours REAL NOT NULL,
                PRIMARY KEY (start_time, publish_time)
            );
        """)
        # Indexes to make cutoff filtering and delivery day lookups fast
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecasts_publish_time
            ON forecasts_wind (publish_time);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecasts_start_time
            ON forecasts_wind (start_time);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecasts_compound
            ON forecasts_wind (start_time, publish_time);
        """)
    conn.close()
    logger.info("Initialized SQLite database schema at %s", db_path)


def save_actuals(df: pd.DataFrame, db_path: Path | str = DEFAULT_DB_PATH) -> int:
    """Save cleaned actuals DataFrame to SQLite using INSERT OR REPLACE."""
    if df.empty:
        return 0

    init_db(db_path)
    conn = get_sqlite_connection(db_path, read_only=False)

    df_save = df.copy()
    if pd.api.types.is_datetime64_any_dtype(df_save["start_time"]):
        df_save["start_time"] = df_save["start_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    records = df_save[["start_time", "generation_mw", "settlement_date", "settlement_period"]].values.tolist()

    with conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO actuals_wind (start_time, generation_mw, settlement_date, settlement_period)
            VALUES (?, ?, ?, ?);
            """,
            records,
        )
    conn.close()
    logger.info("Saved %d actuals records to %s", len(records), db_path)
    return len(records)


def save_forecasts(df: pd.DataFrame, db_path: Path | str = DEFAULT_DB_PATH) -> int:
    """Save cleaned forecasts DataFrame to SQLite using INSERT OR REPLACE."""
    if df.empty:
        return 0

    init_db(db_path)
    conn = get_sqlite_connection(db_path, read_only=False)

    df_save = df.copy()
    if pd.api.types.is_datetime64_any_dtype(df_save["start_time"]):
        df_save["start_time"] = df_save["start_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if pd.api.types.is_datetime64_any_dtype(df_save["publish_time"]):
        df_save["publish_time"] = df_save["publish_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    records = df_save[["start_time", "publish_time", "generation_mw", "horizon_hours"]].values.tolist()

    with conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO forecasts_wind (start_time, publish_time, generation_mw, horizon_hours)
            VALUES (?, ?, ?, ?);
            """,
            records,
        )
    conn.close()
    logger.info("Saved %d forecast records to %s", len(records), db_path)
    return len(records)
