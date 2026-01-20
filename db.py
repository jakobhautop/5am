from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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
            status TEXT NOT NULL CHECK(status IN ('todo', 'done'))
        )
        """
    )
    connection.commit()


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
        "INSERT INTO todos (text, timestamp, status) VALUES (?, ?, 'todo')",
        (text, timestamp),
    )
    connection.commit()
    return TodoRecord(cursor.lastrowid, text, timestamp, "todo")


def update_status(connection: sqlite3.Connection, todo_id: int, status: str) -> None:
    connection.execute(
        "UPDATE todos SET status = ? WHERE id = ?",
        (status, todo_id),
    )
    connection.commit()
