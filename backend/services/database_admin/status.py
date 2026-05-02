"""
Database Admin — status and connection-test functions.
"""

import os
import logging
from typing import Tuple
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from config.settings import Config, is_docker
from models import db

from .helpers import _redact_uri, _human_size, _short_err

logger = logging.getLogger(__name__)

MIN_POSTGRES_MAJOR = 13


def get_status() -> dict:
    """Return current backend status: type, version, size, table count, health."""
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    backend = "postgresql" if db_uri.startswith("postgresql") else "sqlite"

    info = {
        "backend": backend,
        "uri_redacted": _redact_uri(db_uri),
        "is_docker": is_docker(),
        "table_count": 0,
        "size_bytes": 0,
        "size_human": "0 B",
        "version": None,
        "healthy": False,
        "error": None,
    }

    try:
        engine = db.engine
        with engine.connect() as conn:
            insp = inspect(engine)
            info["table_count"] = len(insp.get_table_names())

            if backend == "sqlite":
                db_path = db_uri.replace("sqlite:///", "")
                if os.path.exists(db_path):
                    info["size_bytes"] = os.path.getsize(db_path)
                row = conn.execute(text("SELECT sqlite_version()")).fetchone()
                info["version"] = f"SQLite {row[0]}" if row else "SQLite"
            else:
                row = conn.execute(text("SELECT version()")).fetchone()
                info["version"] = row[0].split(",")[0] if row else "PostgreSQL"
                row = conn.execute(text(
                    "SELECT pg_database_size(current_database())"
                )).fetchone()
                info["size_bytes"] = int(row[0]) if row else 0

            info["size_human"] = _human_size(info["size_bytes"])
            info["healthy"] = True
    except Exception as e:
        logger.error(f"get_status failed: {e}")
        info["error"] = str(e)

    return info


def test_connection(database_url: str) -> Tuple[bool, str]:
    """Validate a DATABASE_URL by opening a connection and running SELECT 1.
    For PostgreSQL, also checks server version >= MIN_POSTGRES_MAJOR.
    """
    if not database_url or not isinstance(database_url, str):
        return False, "DATABASE_URL is required"

    parsed = urlparse(database_url)
    if parsed.scheme not in ("postgresql", "postgresql+psycopg2", "sqlite"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    try:
        engine = create_engine(
            database_url,
            connect_args={"connect_timeout": 5} if parsed.scheme.startswith("postgresql") else {},
            pool_pre_ping=True,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if parsed.scheme.startswith("postgresql"):
                row = conn.execute(text("SHOW server_version_num")).fetchone()
                if row:
                    try:
                        ver_num = int(row[0])  # e.g. 130012 = 13.12, 160003 = 16.3
                        major = ver_num // 10000
                        if major < MIN_POSTGRES_MAJOR:
                            engine.dispose()
                            return False, (
                                f"PostgreSQL {major} is not supported. "
                                f"UCM requires PostgreSQL {MIN_POSTGRES_MAJOR} or newer."
                            )
                    except (ValueError, TypeError):
                        pass  # don't fail on parse errors, just skip the check
        engine.dispose()
        return True, "Connection successful"
    except SQLAlchemyError as e:
        return False, f"Connection failed: {_short_err(str(e))}"
    except Exception as e:
        return False, f"Connection failed: {_short_err(str(e))}"
