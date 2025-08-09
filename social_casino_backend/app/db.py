# social_casino_2.0/social_casino_backend/app/db.py

import sqlite3
import threading

# Используем thread-local для управления соединениями, чтобы избежать проблем в асинхронной среде
local = threading.local()

DATABASE_URL = "social_casino.db"

def get_db():
    """Возвращает соединение с БД для текущего потока."""
    if not hasattr(local, "db"):
        local.db = sqlite3.connect(DATABASE_URL, check_same_thread=False)
        local.db.row_factory = sqlite3.Row
    return local.db

def init_db():
    """Инициализирует базу данных и создает таблицу пользователей."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL NOT NULL DEFAULT 0.0,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    print("Database initialized.")

def get_or_create_user(user_id: int, username: str | None = None) -> dict:
    """Получает пользователя из БД или создает нового, если он не существует."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if user is None:
        cursor.execute(
            "INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)",
            (user_id, username, 0.0) # Новый пользователь начинает с 0
        )
        db.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    else:
        # Обновляем время последнего визита
        cursor.execute(
            "UPDATE users SET last_seen = CURRENT_TIMESTAMP, username = ? WHERE user_id = ?",
            (username, user_id)
        )
        db.commit()

    return dict(user)


def update_balance(user_id: int, amount: float, is_delta: bool = True) -> float:
    """Обновляет баланс пользователя. is_delta=True добавляет/вычитает сумму."""
    db = get_db()
    cursor = db.cursor()
    if is_delta:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    else:
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
    db.commit()

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()['balance']
    return new_balance

def get_balance(user_id: int) -> float:
    """Получает текущий баланс пользователя."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result['balance'] if result else 0.0