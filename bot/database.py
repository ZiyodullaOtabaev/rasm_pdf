"""
SQLite database operations with proper parameterized queries.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

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


# ========================
# ADMIN STATISTICS
# ========================

def get_admin_summary() -> dict:
    """Get comprehensive admin dashboard stats."""
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
        active_7d = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE updated_at >= datetime('now','-7 days')
        """).fetchone()["c"]
        new_7d = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE created_at >= datetime('now','-7 days')
        """).fetchone()["c"]
        active_30d = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE updated_at >= datetime('now','-30 days')
        """).fetchone()["c"]
        new_30d = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE created_at >= datetime('now','-30 days')
        """).fetchone()["c"]
        # Uses today
        uses_today = con.execute("""
            SELECT COUNT(*) c FROM usage_logs
            WHERE created_at >= datetime('now', 'start of day')
        """).fetchone()["c"]
        # Uses this week
        uses_week = con.execute("""
            SELECT COUNT(*) c FROM usage_logs
            WHERE created_at >= datetime('now', '-7 days')
        """).fetchone()["c"]

    return {
        "total_users": total_users,
        "total_uses": total_uses,
        "active_24h": active_24h,
        "new_24h": new_24h,
        "active_7d": active_7d,
        "new_7d": new_7d,
        "active_30d": active_30d,
        "new_30d": new_30d,
        "uses_today": uses_today,
        "uses_week": uses_week,
    }


def get_action_stats() -> Dict[str, int]:
    """Get total count per action (all time)."""
    with db_connect() as con:
        rows = con.execute("""
            SELECT action, COUNT(*) as cnt
            FROM usage_logs
            GROUP BY action
            ORDER BY cnt DESC
        """).fetchall()
    return {r["action"]: int(r["cnt"]) for r in rows}


def get_hourly_activity(hours: int = 24) -> Dict[int, int]:
    """Get activity by hour for last N hours."""
    with db_connect() as con:
        rows = con.execute("""
            SELECT CAST(substr(created_at, 12, 2) AS INTEGER) as hour, COUNT(*) as cnt
            FROM usage_logs
            WHERE created_at >= datetime('now', ? || ' hours')
            GROUP BY hour
            ORDER BY hour ASC
        """, (f"-{hours}",)).fetchall()
    return {int(r["hour"]): int(r["cnt"]) for r in rows}


def get_growth_stats(days: int = 30) -> List[Tuple[str, int]]:
    """Get daily new user registrations for last N days."""
    with db_connect() as con:
        rows = con.execute("""
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS cnt
            FROM users
            WHERE created_at >= datetime('now', ? || ' day')
            GROUP BY day
            ORDER BY day ASC
        """, (f"-{days}",)).fetchall()
    return [(r["day"], int(r["cnt"])) for r in rows]


def get_retention_rate() -> dict:
    """Calculate user retention: users who came back after first use."""
    with db_connect() as con:
        # Users with more than 1 use
        returning = con.execute("""
            SELECT COUNT(*) c FROM users WHERE uses_count > 1
        """).fetchone()["c"]
        total = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        # Users with 5+ uses (power users)
        power_users = con.execute("""
            SELECT COUNT(*) c FROM users WHERE uses_count >= 5
        """).fetchone()["c"]
    return {
        "total": total,
        "returning": returning,
        "retention_pct": round(returning / max(total, 1) * 100, 1),
        "power_users": power_users,
        "power_pct": round(power_users / max(total, 1) * 100, 1),
    }


def get_broadcast_history(limit: int = 10) -> list:
    """Get recent broadcast history."""
    with db_connect() as con:
        return con.execute("""
            SELECT id, media_type, total, success, failed, created_at
            FROM broadcasts
            ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()


def daily_usage_by_action(days: int = 7) -> Dict[str, Dict[str, int]]:
    """Get daily usage breakdown by action."""
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


def search_user(query: str) -> list:
    """Search users by username, first_name, or user_id."""
    with db_connect() as con:
        # Try as user_id first
        if query.isdigit():
            rows = con.execute(
                "SELECT * FROM users WHERE user_id = ?", (int(query),)
            ).fetchall()
            if rows:
                return rows
        # Search by username or name
        like = f"%{query}%"
        return con.execute("""
            SELECT user_id, COALESCE(username,'') as username,
                   COALESCE(first_name,'') as first_name,
                   COALESCE(last_name,'') as last_name,
                   uses_count, created_at, updated_at
            FROM users
            WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
            ORDER BY uses_count DESC LIMIT 20
        """, (like, like, like)).fetchall()
