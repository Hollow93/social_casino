# social_casino_backend/app/clickhouse_logger.py

import os
import json
import datetime
import asyncio
import httpx
import logging
from typing import Optional, Dict, Any

CLICKHOUSE_ENABLED = os.getenv("CLICKHOUSE_ENABLED", "0") == "1"
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "http://localhost:8123/")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "default")
CLICKHOUSE_TABLE = os.getenv("CLICKHOUSE_TABLE", "game_events")

logger = logging.getLogger("uvicorn.error")

_ensured_lock = asyncio.Lock()
_ensured = False
_payload_is_string: Optional[bool] = None
_last_error: Optional[str] = None


def _auth_tuple():
    return (CLICKHOUSE_USER, CLICKHOUSE_PASSWORD) if (CLICKHOUSE_USER or CLICKHOUSE_PASSWORD) else None


async def _exec(client: httpx.AsyncClient, sql: str, *, database: str | None = None) -> None:
    params = {"query": sql}
    if database:
        params["database"] = database
    r = await client.post(CLICKHOUSE_HOST, params=params, auth=_auth_tuple())
    r.raise_for_status()


async def _fetch_one_text(client: httpx.AsyncClient, sql: str, *, database: str | None = None) -> Optional[str]:
    params = {"query": sql, "default_format": "TabSeparated"}
    if database:
        params["database"] = database
    r = await client.post(CLICKHOUSE_HOST, params=params, auth=_auth_tuple())
    r.raise_for_status()
    txt = r.text.strip()
    return txt if txt else None


async def _ping_with_retries(client: httpx.AsyncClient, attempts: int = 8) -> None:
    delay = 0.5
    last_exc: Optional[Exception] = None
    for _ in range(attempts):
        try:
            await _exec(client, "SELECT 1")
            return
        except Exception as e:
            last_exc = e
            await asyncio.sleep(delay)
            delay = min(delay * 1.8, 5.0)
    raise last_exc if last_exc else RuntimeError("Unknown CH ping error")


async def ensure_clickhouse() -> Dict[str, Any]:
    global _ensured, _payload_is_string, _last_error

    status = {
        "enabled": CLICKHOUSE_ENABLED,
        "host": CLICKHOUSE_HOST,
        "db": CLICKHOUSE_DB,
        "table": CLICKHOUSE_TABLE,
        "created": False,
        "payload_type": None,
        "error": None,
    }

    if not CLICKHOUSE_ENABLED:
        status["error"] = "CLICKHOUSE_ENABLED=0"
        return status

    if _ensured and _payload_is_string is not None:
        status["created"] = True
        status["payload_type"] = "String" if _payload_is_string else "JSON"
        status["error"] = _last_error
        return status

    async with _ensured_lock:
        if _ensured and _payload_is_string is not None:
            status["created"] = True
            status["payload_type"] = "String" if _payload_is_string else "JSON"
            status["error"] = _last_error
            return status

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    await _ping_with_retries(client)
                except Exception as e:
                    _last_error = f"CH ping failed: {e}"
                    logger.warning(_last_error)
                    status["error"] = _last_error
                    return status

                if CLICKHOUSE_DB and CLICKHOUSE_DB != "default":
                    try:
                        await _exec(client, f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DB}")
                    except Exception as e:
                        logger.warning(f"CREATE DATABASE warning: {e}")

                json_created = False
                try:
                    await _exec(client, "SET allow_experimental_object_type = 1")
                    create_json_sql = f"""
                        CREATE TABLE IF NOT EXISTS {CLICKHOUSE_TABLE} (
                            ts DateTime,
                            event_type String,
                            user_id Nullable(Int64),
                            user_source Nullable(String),
                            payload JSON
                        )
                        ENGINE = MergeTree()
                        ORDER BY (ts)
                    """
                    await _exec(client, create_json_sql, database=CLICKHOUSE_DB)
                    json_created = True
                    logger.info("[CH] Table ensured with JSON payload.")
                except Exception as e:
                    logger.warning(f"[CH] JSON payload create failed, fallback to String: {e}")

                if not json_created:
                    create_str_sql = f"""
                        CREATE TABLE IF NOT EXISTS {CLICKHOUSE_TABLE} (
                            ts DateTime,
                            event_type String,
                            user_id Nullable(Int64),
                            user_source Nullable(String),
                            payload String
                        )
                        ENGINE = MergeTree()
                        ORDER BY (ts)
                    """
                    try:
                        await _exec(client, create_str_sql, database=CLICKHOUSE_DB)
                        logger.info("[CH] Table ensured with String payload.")
                    except Exception as e:
                        _last_error = f"CH table create (String) failed: {e}"
                        logger.warning(_last_error)
                        status["error"] = _last_error
                        return status

                dtype = await _fetch_one_text(
                    client,
                    f"SELECT type FROM system.columns "
                    f"WHERE database = '{CLICKHOUSE_DB}' AND table = '{CLICKHOUSE_TABLE}' AND name = 'payload' LIMIT 1"
                )
                if dtype is None:
                    _last_error = "CH system.columns has no payload column row"
                    logger.warning(_last_error)
                    status["error"] = _last_error
                    return status

                t = dtype.strip().lower()
                _payload_is_string = not ("json" in t or "object('json')" in t)
                status["payload_type"] = "String" if _payload_is_string else "JSON"

                _ensured = True
                status["created"] = True
                return status

        except Exception as e:
            _last_error = f"ensure_clickhouse unexpected error: {e}"
            logger.warning(_last_error)
            status["error"] = _last_error
            return status


async def ch_status() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "enabled": CLICKHOUSE_ENABLED,
        "host": CLICKHOUSE_HOST,
        "db": CLICKHOUSE_DB,
        "table": CLICKHOUSE_TABLE,
        "reachable": False,
        "table_exists": False,
        "payload_type": None,
        "last_error": _last_error,
    }
    if not CLICKHOUSE_ENABLED:
        return info

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                await _ping_with_retries(client)
                info["reachable"] = True
            except Exception as e:
                info["last_error"] = f"ch_status ping failed: {e}"
                return info

            exists = await _fetch_one_text(
                client,
                f"SELECT 1 FROM system.tables WHERE database='{CLICKHOUSE_DB}' AND name='{CLICKHOUSE_TABLE}' LIMIT 1"
            )
            info["table_exists"] = exists == "1"

            if info["table_exists"]:
                dtype = await _fetch_one_text(
                    client,
                    f"SELECT type FROM system.columns "
                    f"WHERE database = '{CLICKHOUSE_DB}' AND table = '{CLICKHOUSE_TABLE}' AND name = 'payload' LIMIT 1"
                )
                if dtype:
                    t = dtype.strip().lower()
                    info["payload_type"] = "String" if not ("json" in t or "object('json')" in t) else "JSON"

    except Exception as e:
        info["last_error"] = f"ch_status error: {e}"

    return info


async def log_event(event_type: str, user_id: int | None = None, payload: dict | None = None, user_source: str | None = None) -> None:
    """
    Вставка одной строки JSONEachRow.
    Формат ts: 'YYYY-MM-DD HH:MM:SS'. Если payload-колонка String — сериализуем объект в строку.
    """
    if not CLICKHOUSE_ENABLED:
        return

    status = await ensure_clickhouse()
    if not status.get("created"):
        return

    ts_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    row_payload = (payload or {})
    if _payload_is_string is True:
        row_payload = json.dumps(row_payload, ensure_ascii=False)

    row = {
        "ts": ts_str,
        "event_type": event_type,
        "user_id": user_id,
        "user_source": user_source,
        "payload": row_payload,
    }
    data_to_send = json.dumps(row, ensure_ascii=False) + "\n"

    params = {
        "query": f"INSERT INTO {CLICKHOUSE_TABLE} FORMAT JSONEachRow",
        "database": CLICKHOUSE_DB
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(CLICKHOUSE_HOST, params=params, content=data_to_send.encode("utf-8"), auth=_auth_tuple())
            if resp.status_code >= 400:
                # подробная диагностика ошибки ClickHouse
                logger.warning(f"[CH] insert failed: status={resp.status_code} body={resp.text!r} row={data_to_send!r}")
                resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[CH] insert exception: {e}")
        return
