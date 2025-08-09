# social_casino_backend/app/db.py

import sqlite3
import threading
import os

local = threading.local()
DATABASE_URL = os.getenv("SQLITE_PATH", "social_casino.db")

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    balance     REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance);
"""

def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")  # мс
    conn.row_factory = sqlite3.Row
    conn.executescript(INIT_SQL)
    conn.commit()

def get_db() -> sqlite3.Connection:
    if not hasattr(local, "db"):
        local.db = sqlite3.connect(DATABASE_URL, check_same_thread=False, isolation_level=None)
        _configure_connection(local.db)
    return local.db

def init_db() -> None:
    db = get_db()
    db.executescript(INIT_SQL)
    db.commit()

def get_or_create_user(user_id: int, username: str | None = None) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO users(user_id, username, balance) VALUES(?, ?, 0)",
            (user_id, username)
        )
        db.commit()

def update_balance(user_id: int, amount: float, op: str = "set") -> float:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users(user_id, balance) VALUES(?, 0)", (user_id,))
        db.commit()
        current = 0.0
    else:
        current = float(row["balance"])

    if op == "inc":
        new_balance = current + float(amount)
    elif op == "dec":
        new_balance = current - float(amount)
    else:
        new_balance = float(amount)

    cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    db.commit()

    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    return float(cur.fetchone()["balance"])

def get_balance(user_id: int) -> float:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return float(row["balance"]) if row else 0.0
