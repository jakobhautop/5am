from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class TodoRecord:
    todo_id: int
    text: str
    timestamp: str
    status: str


def get_db_path() -> Path:
    data_root = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    db_dir = data_root / "5am"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "5am.db"


def connect_db() -> sqlite3.Connection:
    db_path = get_db_path()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    initialize_db(connection)
    return connection


def initialize_db(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('todo', 'done')),
            completed_timestamp TEXT
        )
        """
    )
    ensure_completed_timestamp_column(connection)
    connection.commit()


def ensure_completed_timestamp_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(todos)").fetchall()
    }
    if "completed_timestamp" in columns:
        return
    connection.execute("ALTER TABLE todos ADD COLUMN completed_timestamp TEXT")


def list_todos(connection: sqlite3.Connection, status: str) -> Iterable[TodoRecord]:
    rows = connection.execute(
        "SELECT id, text, timestamp, status FROM todos WHERE status = ? ORDER BY id",
        (status,),
    ).fetchall()
    return [
        TodoRecord(
            todo_id=row["id"],
            text=row["text"],
            timestamp=row["timestamp"],
            status=row["status"],
        )
        for row in rows
    ]


def add_todo(connection: sqlite3.Connection, text: str) -> TodoRecord:
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO todos (text, timestamp, status, completed_timestamp)
        VALUES (?, ?, 'todo', NULL)
        """,
        (text, timestamp),
    )
    connection.commit()
    return TodoRecord(cursor.lastrowid, text, timestamp, "todo")


def update_status(connection: sqlite3.Connection, todo_id: int, status: str) -> None:
    completed_timestamp = (
        datetime.now(tz=timezone.utc).isoformat() if status == "done" else None
    )
    connection.execute(
        "UPDATE todos SET status = ?, completed_timestamp = ? WHERE id = ?",
        (status, completed_timestamp, todo_id),
    )
    connection.commit()


def delete_todo(connection: sqlite3.Connection, todo_id: int) -> None:
    connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    connection.commit()


def list_completed_counts_by_day(
    connection: sqlite3.Connection, days: int = 14
) -> list[int]:
    today = datetime.now(tz=timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    start_timestamp = datetime.combine(
        start_day, datetime.min.time(), tzinfo=timezone.utc
    ).isoformat()
    rows = connection.execute(
        """
        SELECT date(completed_timestamp) AS day, COUNT(*) AS total
        FROM todos
        WHERE completed_timestamp IS NOT NULL AND completed_timestamp >= ?
        GROUP BY day
        ORDER BY day
        """,
        (start_timestamp,),
    ).fetchall()
    totals_by_day = {row["day"]: row["total"] for row in rows}
    return [
        totals_by_day.get((start_day + timedelta(days=offset)).isoformat(), 0)
        for offset in range(days)
    ]
