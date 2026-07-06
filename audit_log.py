"""Structured audit log backed by SQLite (per planning.md storage spec).

Architectural note: the table is created with the FULL schema from
planning.md now -- including columns that Milestones 4 and 5 will fill
(style_score, appeal fields). Creating the complete schema upfront means
later milestones only change what we WRITE, never the table shape, so we
avoid ad-hoc migrations mid-project.
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "provenance.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    content_id       TEXT PRIMARY KEY,
    creator_id       TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    text             TEXT NOT NULL,
    llm_score        REAL,
    llm_reasoning    TEXT,
    style_score      REAL,
    confidence       REAL,
    attribution      TEXT,
    label            TEXT,
    status           TEXT NOT NULL DEFAULT 'classified',
    short_text       INTEGER NOT NULL DEFAULT 0,
    appeal_reasoning TEXT,
    appeal_timestamp TEXT
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(SCHEMA)


def log_classification(record: dict) -> None:
    """Insert one classification record. Keys must match column names."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (content_id, creator_id, timestamp, text, llm_score,
                llm_reasoning, style_score, confidence, attribution,
                label, status, short_text)
               VALUES (:content_id, :creator_id, :timestamp, :text,
                       :llm_score, :llm_reasoning, :style_score,
                       :confidence, :attribution, :label, :status,
                       :short_text)""",
            record,
        )


def get_record(content_id: str) -> dict | None:
    """Fetch one classification record by content_id, or None if unknown."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM audit_log WHERE content_id = ?", (content_id,)
        ).fetchone()
    return dict(row) if row else None


def record_appeal(content_id: str, reasoning: str, timestamp: str) -> None:
    """Log an appeal alongside the original decision (same record, per spec §4):
    the original scores and label are never separated from the contest."""
    with _connect() as conn:
        conn.execute(
            """UPDATE audit_log
               SET status = 'under_review',
                   appeal_reasoning = ?,
                   appeal_timestamp = ?
               WHERE content_id = ?""",
            (reasoning, timestamp, content_id),
        )


def get_log(limit: int = 20) -> list[dict]:
    """Most recent entries, newest first. Full text is truncated for readability."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        if entry.get("text") and len(entry["text"]) > 120:
            entry["text"] = entry["text"][:120] + "..."
        entries.append(entry)
    return entries