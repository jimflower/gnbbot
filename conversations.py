"""
Persistent conversation history — SQLite-backed, survives service restarts.
Inspired by OpenClaw's session persistence and compaction model.
"""

import os
import sqlite3
import time

from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "conversations.db")

# Max messages to keep in DB per user before pruning oldest
MAX_HISTORY = 30


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                user_id    TEXT NOT NULL,
                idx        INTEGER NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (user_id, idx)
            )
        """)


def load_history(user_id: str) -> list[dict]:
    """Return stored messages for a user, ordered oldest-first."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE user_id = ? ORDER BY idx",
            (user_id,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def save_history(user_id: str, messages: list[dict]):
    """Replace stored history for a user, pruning to MAX_HISTORY."""
    keep = messages[-MAX_HISTORY:]
    now  = time.time()
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        for i, msg in enumerate(keep):
            conn.execute(
                "INSERT INTO conversations (user_id, idx, role, content, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (user_id, i, msg["role"], msg["content"], now),
            )


def clear_history(user_id: str):
    """Delete all stored messages for a user."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))


def get_stats(user_id: str) -> dict:
    """Return basic stats about the stored conversation."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MIN(created_at) as first"
            " FROM conversations WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    count = row["cnt"]
    first = row["first"]
    if first:
        age_h = (time.time() - first) / 3600
        age_str = f"{age_h:.0f}h" if age_h < 48 else f"{age_h/24:.0f}d"
    else:
        age_str = "—"
    return {"message_count": count, "history_age": age_str}


init_db()
