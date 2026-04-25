from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    input_path TEXT,
    output_path TEXT,
    error TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


def init_db(db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def create_job(db_path: str | Path, job_id: str, input_path: str, meta: dict[str, Any] | None = None) -> None:
    now = time.time()
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, status, progress, message, input_path, meta_json, created_at, updated_at)
            VALUES (?, 'queued', 0, 'Queued', ?, ?, ?, ?)
            """,
            (job_id, input_path, json.dumps(meta or {}), now, now),
        )
        conn.commit()


def update_job(db_path: str | Path, job_id: str, **fields: Any) -> None:
    if not fields:
        return
    init_db(db_path)
    fields["updated_at"] = time.time()
    allowed = {"status", "progress", "message", "input_path", "output_path", "error", "meta_json", "updated_at"}
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "meta_json" and not isinstance(value, str):
            value = json.dumps(value)
        assignments.append(f"{key} = ?")
        values.append(value)
    if not assignments:
        return
    values.append(job_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values)
        conn.commit()


def get_job(db_path: str | Path, job_id: str) -> dict[str, Any] | None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    try:
        data["meta"] = json.loads(data.pop("meta_json") or "{}")
    except json.JSONDecodeError:
        data["meta"] = {}
    return data


def list_jobs(db_path: str | Path, limit: int = 25) -> list[dict[str, Any]]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        try:
            item["meta"] = json.loads(item.pop("meta_json") or "{}")
        except json.JSONDecodeError:
            item["meta"] = {}
        jobs.append(item)
    return jobs
