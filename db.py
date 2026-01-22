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
    parent_id: int | None
    sort_order: float
    priority: int | None


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
    connection.execute("PRAGMA foreign_keys = ON")
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
            completed_timestamp TEXT,
            parent_id INTEGER,
            sort_order REAL,
            priority INTEGER,
            FOREIGN KEY(parent_id) REFERENCES todos(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS focus_time (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            todo_id INTEGER NOT NULL,
            focus_date TEXT NOT NULL,
            seconds INTEGER NOT NULL DEFAULT 0,
            UNIQUE(todo_id, focus_date),
            FOREIGN KEY(todo_id) REFERENCES todos(id) ON DELETE CASCADE
        )
        """
    )
    ensure_completed_timestamp_column(connection)
    ensure_parent_id_column(connection)
    ensure_sort_order_column(connection)
    ensure_priority_column(connection)
    connection.commit()


def ensure_completed_timestamp_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(todos)").fetchall()
    }
    if "completed_timestamp" in columns:
        return
    connection.execute("ALTER TABLE todos ADD COLUMN completed_timestamp TEXT")


def ensure_parent_id_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(todos)").fetchall()
    }
    if "parent_id" in columns:
        return
    connection.execute("ALTER TABLE todos ADD COLUMN parent_id INTEGER")


def ensure_sort_order_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(todos)").fetchall()
    }
    if "sort_order" not in columns:
        connection.execute("ALTER TABLE todos ADD COLUMN sort_order REAL")
    connection.execute("UPDATE todos SET sort_order = id WHERE sort_order IS NULL")


def ensure_priority_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(todos)").fetchall()
    }
    if "priority" in columns:
        return
    connection.execute("ALTER TABLE todos ADD COLUMN priority INTEGER")


def list_todos(connection: sqlite3.Connection, status: str) -> Iterable[TodoRecord]:
    rows = connection.execute(
        """
        SELECT id, text, timestamp, status, parent_id, sort_order, priority
        FROM todos
        WHERE status = ?
        ORDER BY sort_order, id
        """,
        (status,),
    ).fetchall()
    return [
        TodoRecord(
            todo_id=row["id"],
            text=row["text"],
            timestamp=row["timestamp"],
            status=row["status"],
            parent_id=row["parent_id"],
            sort_order=row["sort_order"] if row["sort_order"] is not None else row["id"],
            priority=row["priority"],
        )
        for row in rows
    ]


def add_todo(
    connection: sqlite3.Connection,
    text: str,
    status: str = "todo",
    parent_id: int | None = None,
    sort_order: float | None = None,
    priority: int | None = None,
) -> TodoRecord:
    if sort_order is None:
        row = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS max_order FROM todos WHERE status = ?",
            (status,),
        ).fetchone()
        sort_order = float(row["max_order"]) + 1
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO todos (text, timestamp, status, completed_timestamp, parent_id, sort_order, priority)
        VALUES (?, ?, ?, NULL, ?, ?, ?)
        """,
        (text, timestamp, status, parent_id, sort_order, priority),
    )
    connection.commit()
    return TodoRecord(
        cursor.lastrowid,
        text,
        timestamp,
        status,
        parent_id,
        sort_order,
        priority,
    )


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
    connection.execute("UPDATE todos SET parent_id = NULL WHERE parent_id = ?", (todo_id,))
    connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    connection.commit()


def update_parent(
    connection: sqlite3.Connection, todo_id: int, parent_id: int | None
) -> None:
    connection.execute(
        "UPDATE todos SET parent_id = ? WHERE id = ?",
        (parent_id, todo_id),
    )
    connection.commit()


def update_priority(
    connection: sqlite3.Connection, todo_id: int, priority: int | None
) -> None:
    connection.execute(
        "UPDATE todos SET priority = ? WHERE id = ?",
        (priority, todo_id),
    )
    connection.commit()


def update_text(connection: sqlite3.Connection, todo_id: int, text: str) -> None:
    connection.execute(
        "UPDATE todos SET text = ? WHERE id = ?",
        (text, todo_id),
    )
    connection.commit()


def list_created_counts_by_day(
    connection: sqlite3.Connection, days: int = 14
) -> list[int]:
    today = datetime.now(tz=timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    start_timestamp = datetime.combine(
        start_day, datetime.min.time(), tzinfo=timezone.utc
    ).isoformat()
    rows = connection.execute(
        """
        SELECT date(timestamp) AS day, COUNT(*) AS total
        FROM todos
        WHERE timestamp >= ?
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


def add_focus_seconds(
    connection: sqlite3.Connection, todo_id: int, seconds: int
) -> None:
    focus_date = datetime.now(tz=timezone.utc).date().isoformat()
    connection.execute(
        """
        INSERT INTO focus_time (todo_id, focus_date, seconds)
        VALUES (?, ?, ?)
        ON CONFLICT(todo_id, focus_date)
        DO UPDATE SET seconds = seconds + excluded.seconds
        """,
        (todo_id, focus_date, seconds),
    )
    connection.commit()


def list_focus_minutes_by_day(
    connection: sqlite3.Connection, days: int = 14
) -> list[int]:
    today = datetime.now(tz=timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    start_date = start_day.isoformat()
    rows = connection.execute(
        """
        SELECT focus_date AS day, SUM(seconds) AS total_seconds
        FROM focus_time
        WHERE focus_date >= ?
        GROUP BY day
        ORDER BY day
        """,
        (start_date,),
    ).fetchall()
    totals_by_day = {row["day"]: row["total_seconds"] for row in rows}
    return [
        int(totals_by_day.get((start_day + timedelta(days=offset)).isoformat(), 0) // 60)
        for offset in range(days)
    ]
