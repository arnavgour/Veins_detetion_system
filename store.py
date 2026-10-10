"""SQLite persistence for extracted vein features."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "vena.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    source TEXT NOT NULL,
    invert INTEGER NOT NULL DEFAULT 0,
    width INTEGER,
    height INTEGER,
    endpoints INTEGER,
    branches INTEGER,
    skeleton_pixels INTEGER,
    vein_pixels INTEGER,
    elapsed_ms REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS landmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_landmarks_analysis ON landmarks(analysis_id);
CREATE INDEX IF NOT EXISTS idx_analyses_source_file ON analyses(source, filename);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_analysis(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "source": row["source"],
        "invert": bool(row["invert"]),
        "width": row["width"],
        "height": row["height"],
        "endpoints": row["endpoints"],
        "branches": row["branches"],
        "skeleton_pixels": row["skeleton_pixels"],
        "vein_pixels": row["vein_pixels"],
        "elapsed_ms": row["elapsed_ms"],
        "created_at": row["created_at"],
    }


def save_analysis(
    filename: str,
    source: str,
    invert: bool,
    features: dict[str, Any],
) -> int:
    metrics = features.get("metrics") or {}
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO analyses (
                filename, source, invert, width, height,
                endpoints, branches, skeleton_pixels, vein_pixels,
                elapsed_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                source,
                1 if invert else 0,
                metrics.get("width"),
                metrics.get("height"),
                metrics.get("endpoints", len(features.get("endpoints") or [])),
                metrics.get("branches", len(features.get("branches") or [])),
                metrics.get("skeleton_pixels"),
                metrics.get("vein_pixels"),
                metrics.get("elapsed_ms"),
                created_at,
            ),
        )
        analysis_id = int(cur.lastrowid)
        points = [
            (analysis_id, "endpoint", int(p["x"]), int(p["y"]))
            for p in features.get("endpoints") or []
        ]
        points += [
            (analysis_id, "branch", int(p["x"]), int(p["y"]))
            for p in features.get("branches") or []
        ]
        if points:
            conn.executemany(
                "INSERT INTO landmarks (analysis_id, kind, x, y) VALUES (?, ?, ?, ?)",
                points,
            )
        return analysis_id


def list_analyses() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY datetime(created_at) DESC, id DESC"
        ).fetchall()
    return [_row_to_analysis(row) for row in rows]


def get_analysis(analysis_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            return None
        points = conn.execute(
            "SELECT kind, x, y FROM landmarks WHERE analysis_id = ? ORDER BY kind, id",
            (analysis_id,),
        ).fetchall()
    payload = _row_to_analysis(row)
    payload["endpoint_points"] = [
        {"x": p["x"], "y": p["y"]} for p in points if p["kind"] == "endpoint"
    ]
    payload["branch_points"] = [
        {"x": p["x"], "y": p["y"]} for p in points if p["kind"] == "branch"
    ]
    return payload


def delete_analysis(analysis_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        return cur.rowcount > 0


def has_sample(filename: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM analyses WHERE source = 'sample' AND filename = ? LIMIT 1",
            (filename,),
        ).fetchone()
    return row is not None
