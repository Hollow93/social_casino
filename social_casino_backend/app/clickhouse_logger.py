# social_casino_2.0/social_casino_backend/app/clickhouse_logger.py

import httpx
import json
import datetime
import asyncio

# --- КОНФИГУРАЦИЯ ---
# Замените на ваши реальные данные от ClickHouse
CLICKHOUSE_HOST = "http://localhost:8123/" # <-- ЗАМЕНИТЕ
CLICKHOUSE_USER = "default"                # <-- ЗАМЕНИТЕ
CLICKHOUSE_PASSWORD = ""                   # <-- ЗАМЕНИТЕ
CLICKHOUSE_DB = "default"                  # <-- ЗАМЕНИТЕ (если нужно)
CLICKHOUSE_TABLE = "game_events"

# Создайте эту таблицу в ClickHouse:
# CREATE TABLE IF NOT EXISTS game_events (
#     event_timestamp DateTime,
#     user_id UInt64,
#     event_name String,
#     event_data String,
#     user_source Nullable(String)
# ) ENGINE = MergeTree()
# ORDER BY (event_timestamp, user_id);

async def send_event_async(user_id: int, event_name: str, event_data: dict, user_source: str = None):
    """
    Асинхронно отправляет событие в ClickHouse.
    """
    print(f"[Analytics] Event: {event_name}, User: {user_id}, Data: {event_data}")
    
    try:
        # Преобразуем все значения в event_data в строки, чтобы избежать проблем с JSON
        event_data_str = {k: str(v) for k, v in event_data.items()}

        row = {
            "event_timestamp": datetime.datetime.now().isoformat(timespec='seconds'),
            "user_id": user_id,
            "event_name": event_name,
            "event_data": json.dumps(event_data_str),
            "user_source": user_source
        }
        
        # ClickHouse ожидает данные в формате JSONEachRow, где каждая строка - отдельный JSON объект
        data_to_send = json.dumps(row) + '\n'

        async with httpx.AsyncClient() as client:
            response = await client.post(
                CLICKHOUSE_HOST,
                params={
                    "query": f"INSERT INTO {CLICKHOUSE_TABLE} FORMAT JSONEachRow",
                    "database": CLICKHOUSE_DB
                },
                content=data_to_send,
                auth=(CLICKHOUSE_USER, CLICKHOUSE_PASSWORD),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status() # Проверит, был ли запрос успешным (код 2xx)

    except Exception as e:
        print(f"[Analytics ERROR] Failed to send event: {e}")

def log_event(user_id: int, event_name: str, event_data: dict, user_source: str = None):
    """
    Создает фоновую задачу для отправки события, не блокируя основной поток.
    """
    asyncio.create_task(send_event_async(user_id, event_name, event_data, user_source))