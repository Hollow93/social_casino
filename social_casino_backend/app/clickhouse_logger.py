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
CLICKHOUSE_LOG_TABLE = os.getenv("CLICKHOUSE_TABLE", "game_events")
CLICKHOUSE_SPINS_TABLE = os.getenv("CLICKHOUSE_SPINS_TABLE", "spins")

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

async def _fetch_text(client: httpx.AsyncClient, sql: str, *, database: str | None = None) -> str:
    params = {"query": sql, "default_format": "TabSeparated"}
    if database:
        params["database"] = database
    r = await client.post(CLICKHOUSE_HOST, params=params, auth=_auth_tuple())
    r.raise_for_status()
    return r.text.strip()

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
    """
    Больше НЕ создаём таблицы здесь — этим занимаются миграции.
    Только пингуем и определяем тип payload (String/JSON), чтобы корректно сериализовать.
    """
    global _ensured, _payload_is_string, _last_error

    status = {
        "enabled": CLICKHOUSE_ENABLED,
        "host": CLICKHOUSE_HOST,
        "db": CLICKHOUSE_DB,
        "log_table": CLICKHOUSE_LOG_TABLE,
        "spins_table": CLICKHOUSE_SPINS_TABLE,
        "reachable": False,
        "payload_type": None,
        "error": None,
    }
    if not CLICKHOUSE_ENABLED:
        status["error"] = "CLICKHOUSE_ENABLED=0"
        return status

    if _ensured and _payload_is_string is not None:
        status["reachable"] = True
        status["payload_type"] = "String" if _payload_is_string else "JSON"
        return status

    async with _ensured_lock:
        if _ensured and _payload_is_string is not None:
            status["reachable"] = True
            status["payload_type"] = "String" if _payload_is_string else "JSON"
            return status
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await _ping_with_retries(client)
                status["reachable"] = True

                try:
                    dtype = await _fetch_text(
                        client,
                        f"SELECT type FROM system.columns "
                        f"WHERE database = '{CLICKHOUSE_DB}' AND table = '{CLICKHOUSE_LOG_TABLE}' AND name = 'payload' LIMIT 1"
                    )
                    t = (dtype or "").strip().lower()
                    _payload_is_string = not ("json" in t or "object('json')" in t)
                    status["payload_type"] = "String" if _payload_is_string else "JSON"
                except Exception as e:
                    _payload_is_string = True
                    status["payload_type"] = "String"
                    _last_error = f"payload type detect failed: {e}"
                    status["error"] = _last_error

                _ensured = True
                return status
        except Exception as e:
            _last_error = f"CH ping failed: {e}"
            status["error"] = _last_error
            return status

async def ch_status() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "enabled": CLICKHOUSE_ENABLED,
        "host": CLICKHOUSE_HOST,
        "db": CLICKHOUSE_DB,
        "log_table": CLICKHOUSE_LOG_TABLE,
        "spins_table": CLICKHOUSE_SPINS_TABLE,
        "reachable": False,
        "payload_type": "String" if (_payload_is_string is True) else ("JSON" if _payload_is_string is False else None),
        "last_error": _last_error,
    }
    if not CLICKHOUSE_ENABLED:
        return info
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await _ping_with_retries(client)
            info["reachable"] = True
    except Exception as e:
        info["last_error"] = f"ch_status ping failed: {e}"
    return info

async def log_event(event_type: str, user_id: int | None = None, payload: dict | None = None, user_source: str | None = None) -> None:
    if not CLICKHOUSE_ENABLED:
        return
    st = await ensure_clickhouse()
    if not st.get("reachable"):
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
    params = {"query": f"INSERT INTO {CLICKHOUSE_LOG_TABLE} FORMAT JSONEachRow", "database": CLICKHOUSE_DB}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(CLICKHOUSE_HOST, params=params, content=data_to_send.encode("utf-8"), auth=_auth_tuple())
            if resp.status_code >= 400:
                logger.warning(f"[CH] insert game_events failed: status={resp.status_code} body={resp.text!r} row={data_to_send!r}")
                resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[CH] insert game_events exception: {e}")

async def log_spin(*, user_id: str, event_type: str, amount: float, multiplier: float, timestamp: datetime.datetime | None = None) -> None:
    if not CLICKHOUSE_ENABLED:
        return
    st = await ensure_clickhouse()
    if not st.get("reachable"):
        return

    ts = timestamp or datetime.datetime.utcnow()
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "user_id": str(user_id),
        "event_type": event_type,
        "amount": float(amount),
        "multiplier": float(multiplier),
        "timestamp": ts_str,
    }
    data_to_send = json.dumps(row, ensure_ascii=False) + "\n"
    params = {"query": f"INSERT INTO {CLICKHOUSE_SPINS_TABLE} FORMAT JSONEachRow", "database": CLICKHOUSE_DB}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(CLICKHOUSE_HOST, params=params, content=data_to_send.encode("utf-8"), auth=_auth_tuple())
            if resp.status_code >= 400:
                logger.warning(f"[CH] insert spins failed: status={resp.status_code} body={resp.text!r} row={data_to_send!r}")
                resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[CH] insert spins exception: {e}")
