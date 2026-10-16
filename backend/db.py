"""Small SQLite data layer for captures and lecture-level notes."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DB_PATH, RECEIVED_DIR


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_columns():
    with _connect() as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(frames)").fetchall()]
        additions = (
            ("ocr_confidence", "REAL DEFAULT 0"),
            ("ocr_engine", "TEXT DEFAULT 'tesseract'"),
            ("ocr_status", "TEXT DEFAULT 'pending'"),
            ("processed_image_path", "TEXT DEFAULT ''"),
            ("last_error", "TEXT DEFAULT ''"),
            ("sharpness", "REAL DEFAULT 0"),
            ("stability_score", "REAL DEFAULT 0"),
            ("lecture_id", "INTEGER"),
        )
        for name, sql_type in additions:
            if name not in columns:
                conn.execute(f"ALTER TABLE frames ADD COLUMN {name} {sql_type}")


def init_db():
    with _connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS lectures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT DEFAULT '',
            started_at TEXT NOT NULL,
            ended_at TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            generation_status TEXT DEFAULT 'not_generated',
            generation_error TEXT DEFAULT '',
            source_count INTEGER DEFAULT 0,
            generated_at TEXT DEFAULT ''
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            received_at TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            device TEXT,
            change_score REAL,
            board_visibility REAL,
            brightness REAL,
            sharpness REAL DEFAULT 0,
            stability_score REAL DEFAULT 0,
            timestamp_device TEXT,
            processing_status TEXT NOT NULL DEFAULT 'received',
            ocr_text TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            structured_json TEXT DEFAULT '{}',
            processing_error TEXT DEFAULT '',
            ocr_confidence REAL DEFAULT 0,
            ocr_engine TEXT DEFAULT 'tesseract',
            ocr_status TEXT DEFAULT 'received',
            processed_image_path TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            lecture_id INTEGER REFERENCES lectures(id) ON DELETE SET NULL
        )
        """)
    _ensure_columns()
    purge_missing_frames()


def _frame_dict(row):
    if row is None:
        return None
    item = dict(row)
    item["image_available"] = bool(item.get("filename") and (RECEIVED_DIR / Path(item["filename"]).name).exists())
    try:
        item["structured"] = json.loads(item.pop("structured_json", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        item["structured"] = {}
        item.pop("structured_json", None)
    return item


def purge_missing_frames():
    with _connect() as conn:
        rows = conn.execute("SELECT id, filename FROM frames").fetchall()
        for row in rows:
            if not (RECEIVED_DIR / Path(row["filename"]).name).exists():
                conn.execute("DELETE FROM frames WHERE id = ?", (row["id"],))


def create_lecture(title: str, subject: str = ""):
    title = (title or "").strip()[:120]
    subject = (subject or "").strip()[:120]
    if not title:
        raise ValueError("Please enter a lecture title.")
    with _connect() as conn:
        active = conn.execute("SELECT id FROM lectures WHERE status='active' LIMIT 1").fetchone()
        if active:
            raise ValueError("End the current lecture before starting another one.")
        cur = conn.execute(
            "INSERT INTO lectures (title, subject, started_at, status) VALUES (?, ?, ?, 'active')",
            (title, subject, _now()),
        )
        lecture_id = cur.lastrowid
    return get_lecture(lecture_id)


def end_lecture(lecture_id: int):
    with _connect() as conn:
        row = conn.execute("SELECT id, status FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if not row:
            return None
        if row["status"] == "active":
            conn.execute("UPDATE lectures SET status='completed', ended_at=? WHERE id=?", (_now(), lecture_id))
    return get_lecture(lecture_id)


def get_active_lecture():
    with _connect() as conn:
        row = conn.execute("SELECT * FROM lectures WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def get_lecture(lecture_id: int, include_frames: bool = True):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if not row:
            return None
        lecture = dict(row)
        lecture["frame_count"] = conn.execute("SELECT COUNT(*) FROM frames WHERE lecture_id=?", (lecture_id,)).fetchone()[0]
        lecture["ready_count"] = conn.execute(
            "SELECT COUNT(*) FROM frames WHERE lecture_id=? AND TRIM(COALESCE(ocr_text,''))<>'' AND ocr_status IN ('ok','complete','low_confidence')",
            (lecture_id,),
        ).fetchone()[0]
        if include_frames:
            rows = conn.execute("SELECT * FROM frames WHERE lecture_id=? ORDER BY id ASC", (lecture_id,)).fetchall()
            lecture["frames"] = [_frame_dict(r) for r in rows]
    return lecture


def list_lectures(limit: int = 50):
    with _connect() as conn:
        rows = conn.execute("""
            SELECT l.*,
                   (SELECT COUNT(*) FROM frames f WHERE f.lecture_id=l.id) AS frame_count,
                   (SELECT COUNT(*) FROM frames f WHERE f.lecture_id=l.id AND TRIM(COALESCE(f.ocr_text,''))<>'') AS ready_count
            FROM lectures l ORDER BY l.id DESC LIMIT ?
        """, (max(1, min(100, int(limit))),)).fetchall()
    return [dict(row) for row in rows]


def save_lecture_notes(lecture_id: int, summary: str, notes: str, source_count: int, error: str = ""):
    status = "failed" if error else "complete"
    with _connect() as conn:
        conn.execute("""
            UPDATE lectures SET summary=?, notes=?, source_count=?, generation_status=?,
                generation_error=?, generated_at=? WHERE id=?
        """, (summary, notes, source_count, status, error, _now() if not error else "", lecture_id))
        exists = conn.execute("SELECT changes()").fetchone()[0]
    return get_lecture(lecture_id) if exists else None


def get_lecture_context(lecture_id: int):
    """Return usable OCR text in capture order, skipping failed/empty captures."""
    with _connect() as conn:
        lecture = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if not lecture:
            return None, []
        rows = conn.execute("""
            SELECT id, filename, received_at, ocr_text, ocr_status
            FROM frames WHERE lecture_id=? AND TRIM(COALESCE(ocr_text,''))<>''
            ORDER BY id ASC
        """, (lecture_id,)).fetchall()
    return dict(lecture), [dict(row) for row in rows]


def insert_frame(filename, size_bytes, headers):
    clean_name = Path(filename or "").name.replace("..", "_")
    now = _now()

    def number(name):
        try:
            return float(headers.get(name))
        except (TypeError, ValueError):
            return None

    with _connect() as conn:
        active = conn.execute("SELECT id FROM lectures WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        lecture_id = active["id"] if active else None
        cur = conn.execute("""
            INSERT INTO frames
            (filename, received_at, size_bytes, device, change_score, board_visibility,
             brightness, sharpness, stability_score, timestamp_device, lecture_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (clean_name, now, size_bytes, headers.get("X-Device"), number("X-Change-Score"),
              number("X-Board-Visibility"), number("X-Brightness"), number("X-Sharpness"),
              number("X-Stability-Score"), headers.get("X-Timestamp"), lecture_id))
        return cur.lastrowid


def list_frames(limit=50):
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM frames ORDER BY id DESC LIMIT ?", (max(1, min(1000, int(limit))),)).fetchall()
    return [item for item in (_frame_dict(row) for row in rows) if item and item["image_available"]]


def get_frame(frame_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM frames WHERE id=?", (frame_id,)).fetchone()
    frame = _frame_dict(row)
    if frame and not frame["image_available"]:
        return None
    return frame


def set_processing(frame_id, status="processing"):
    with _connect() as conn:
        conn.execute("UPDATE frames SET processing_status=?, ocr_status=?, processing_error='', last_error='' WHERE id=?",
                     (status or "processing", status or "processing", frame_id))


def update_processing(frame_id, result=None, error=""):
    if error:
        with _connect() as conn:
            conn.execute("UPDATE frames SET processing_status='failed', ocr_status='failed', processing_error=?, last_error=? WHERE id=?",
                         (error, error, frame_id))
        return
    if result is None:
        return
    status = result.get("ocr_status", "complete")
    processing_status = "complete" if status in {"ok", "complete"} else status
    if status not in {"ok", "complete", "low_confidence", "no_text", "missing_tesseract", "failed", "error"}:
        processing_status = "failed"
    with _connect() as conn:
        conn.execute("""
            UPDATE frames SET processing_status=?, ocr_text=?, summary=?, notes=?, structured_json=?,
                processing_error=?, ocr_confidence=?, ocr_engine='tesseract', ocr_status=?,
                processed_image_path=?, last_error=? WHERE id=?
        """, (processing_status, result.get("ocr_text", ""), result.get("summary", ""),
              result.get("notes", ""), json.dumps(result.get("structured", {}), ensure_ascii=False),
              result.get("ocr_error", ""), float(result.get("ocr_confidence", 0.0) or 0.0), status,
              result.get("binary_image", ""), result.get("ocr_error", ""), frame_id))
