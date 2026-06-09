"""
SQLite database operations with proper parameterized queries.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from bot.config import DB_PATH

logger = logging.getLogger(__name__)


def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def db_init():
    """Initialize database tables."""
    with db_connect() as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            uses_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            media_type TEXT,
            file_id TEXT,
            caption TEXT,
            total INTEGER DEFAULT 0,
            success INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_logs(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_logs(created_at)")
        con.commit()
    logger.info("Database initialized successfully")


def upsert_user(user_id: int, username: Optional[str] = None,
                first_name: Optional[str] = None, last_name: Optional[str] = None):
    """Insert or update user record."""
    with db_connect() as con:
        con.execute("""
        INSERT INTO users (user_id, username, first_name, last_name, uses_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, datetime('now'), datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            updated_at=datetime('now')
        """, (user_id, username, first_name, last_name))
        con.commit()


def get_uses(user_id: int) -> int:
    """Get total uses count for a user."""
    with db_connect() as con:
        row = con.execute("SELECT uses_count FROM users WHERE user_id=?", (user_id,)).fetchone()
        return int(row["uses_count"]) if row and row["uses_count"] is not None else 0


def inc_uses_and_log(user_id: int, action: str):
    """Increment uses counter and log the action."""
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as con:
        con.execute(
            "UPDATE users SET uses_count = COALESCE(uses_count,0)+1, updated_at=datetime('now') WHERE user_id=?",
            (user_id,)
        )
        con.execute(
            "INSERT INTO usage_logs (user_id, action, created_at) VALUES (?, ?, ?)",
            (user_id, action, now)
        )
        con.commit()


def get_all_user_ids() -> List[int]:
    """Get all registered user IDs."""
    with db_connect() as con:
        rows = con.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


def save_broadcast_result(admin_id: int, media_type: str, file_id: str,
                          caption: str, total: int, success: int, failed: int):
    """Save broadcast result to database."""
    with db_connect() as con:
        con.execute("""
        INSERT INTO broadcasts (admin_id, media_type, file_id, caption, total, success, failed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (admin_id, media_type, file_id, caption, total, success, failed))
        con.commit()


def get_admin_summary() -> tuple:
    """Get admin dashboard summary stats."""
    with db_connect() as con:
        total_users = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_uses = con.execute("SELECT COALESCE(SUM(uses_count),0) s FROM users").fetchone()["s"]
        active_24h = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE updated_at >= datetime('now','-24 hours')
        """).fetchone()["c"]
        new_24h = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE created_at >= datetime('now','-24 hours')
        """).fetchone()["c"]
    return total_users, total_uses, active_24h, new_24h


def daily_usage_by_action(days: int = 7) -> Dict[str, Dict[str, int]]:
    """
    Get daily usage breakdown by action.
    Uses parameterized query to prevent SQL injection.
    """
    with db_connect() as con:
        rows = con.execute("""
            SELECT substr(created_at, 1, 10) AS day, action, COUNT(*) AS cnt
            FROM usage_logs
            WHERE created_at >= datetime('now', ? || ' day')
            GROUP BY day, action
            ORDER BY day ASC
        """, (f"-{days}",)).fetchall()
    data: Dict[str, Dict[str, int]] = {}
    for r in rows:
        data.setdefault(r["day"], {})[r["action"]] = int(r["cnt"])
    return data


def get_top_users(limit: int = 30) -> list:
    """Get top users by usage count."""
    with db_connect() as con:
        return con.execute("""
            SELECT user_id, COALESCE(username,'') as username,
                   COALESCE(first_name,'') as first_name,
                   COALESCE(last_name,'') as last_name, uses_count
            FROM users ORDER BY uses_count DESC, updated_at DESC LIMIT ?
        """, (limit,)).fetchall()


def get_active_users_24h(limit: int = 30) -> list:
    """Get users active in last 24 hours."""
    with db_connect() as con:
        return con.execute("""
            SELECT user_id, COALESCE(username,'') as username,
                   COALESCE(first_name,'') as first_name,
                   COALESCE(last_name,'') as last_name, updated_at
            FROM users WHERE updated_at >= datetime('now','-24 hours')
            ORDER BY updated_at DESC LIMIT ?
        """, (limit,)).fetchall()


def get_new_users_24h(limit: int = 30) -> list:
    """Get users registered in last 24 hours."""
    with db_connect() as con:
        return con.execute("""
            SELECT user_id, COALESCE(username,'') as username,
                   COALESCE(first_name,'') as first_name,
                   COALESCE(last_name,'') as last_name, created_at
            FROM users WHERE created_at >= datetime('now','-24 hours')
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
