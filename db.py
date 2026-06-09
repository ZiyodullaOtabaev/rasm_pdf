import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "bot.db"

def _connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with _connect() as con:
        cur = con.cursor()

        # users table (sizda bor bo‘lsa ham, xavfsiz)
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

        # usage logs
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        # Indexlar tezlik uchun
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_logs(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_logs(created_at)")
        con.commit()

def upsert_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    with _connect() as con:
        cur = con.cursor()
        cur.execute("""
        INSERT INTO users (user_id, username, first_name, last_name, uses_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, datetime('now'), datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
          username=excluded.username,
          first_name=excluded.first_name,
          last_name=excluded.last_name,
          updated_at=datetime('now')
        """, (user_id, username, first_name, last_name))
        con.commit()

def inc_uses_and_log(user_id: int, action: str):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        cur = con.cursor()
        cur.execute("UPDATE users SET uses_count = COALESCE(uses_count,0) + 1, updated_at=datetime('now') WHERE user_id=?", (user_id,))
        cur.execute("INSERT INTO usage_logs (user_id, action, created_at) VALUES (?, ?, ?)", (user_id, action, now))
        con.commit()

def get_user_uses(user_id: int) -> int:
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT uses_count FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return int(row["uses_count"]) if row and row["uses_count"] is not None else 0

def top_users(limit: int = 10):
    with _connect() as con:
        cur = con.cursor()
        cur.execute("""
        SELECT user_id, username, first_name, uses_count
        FROM users
        ORDER BY uses_count DESC
        LIMIT ?
        """, (limit,))
        return cur.fetchall()

def daily_counts(days: int = 7):
    # UTC bo‘yicha kunlik kesim
    with _connect() as con:
        cur = con.cursor()
        cur.execute(f"""
        SELECT substr(created_at, 1, 10) as day, action, COUNT(*) as cnt
        FROM usage_logs
        WHERE created_at >= datetime('now', '-{days} day')
        GROUP BY day, action
        ORDER BY day DESC, cnt DESC
        """)
        return cur.fetchall()

def total_users():
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM users")
        return int(cur.fetchone()["c"])

def total_uses():
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COALESCE(SUM(uses_count),0) AS s FROM users")
        return int(cur.fetchone()["s"])