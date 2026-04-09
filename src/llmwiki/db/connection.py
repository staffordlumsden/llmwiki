"""Database connection management."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional


class DatabaseConnection:
    """Database connection wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Create or return database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def cursor(self):
        """Context manager for database cursor."""
        conn = self.connect()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute a single SQL statement."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)

    def executescript(self, sql: str) -> None:
        """Execute a multi-statement SQL script."""
        conn = self.connect()
        try:
            conn.executescript(sql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """Execute SQL statement with multiple parameter sets."""
        with self.cursor() as cursor:
            cursor.executemany(sql, params_list)
            return cursor

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row:
        """Fetch single row."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all rows."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def fetchone_dict(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Fetch single row as dictionary."""
        result = self.fetchone(sql, params)
        return dict(result) if result else None

    def fetchall_dict(self, sql: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as dictionaries."""
        results = self.fetchall(sql, params)
        return [dict(row) for row in results]


def init_database(db_path: Path) -> DatabaseConnection:
    """Initialize database with schema."""
    from llmwiki import __version__
    
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read schema
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    # Create connection and execute schema
    conn = DatabaseConnection(db_path)
    conn.connect()
    conn.executescript(schema_sql)
    
    # Store version info
    conn.execute(
        "INSERT INTO runs (run_type, profile, status) VALUES (?, ?, ?)",
        ("init", "unknown", "completed")
    )
    
    return conn
