# social_casino_backend/app/migrations_runner.py

import os
import glob
from typing import List, Dict, Any
import datetime
import httpx

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "http://localhost:8123/")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "default")

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")
MIGRATIONS_TABLE = "_migrations"


def _auth_tuple():
    return (CLICKHOUSE_USER, CLICKHOUSE_PASSWORD) if (CLICKHOUSE_USER or CLICKHOUSE_PASSWORD) else None


async def _exec_sql(client: httpx.AsyncClient, sql: str, *, database: str | None = None) -> None:
    params = {"query": sql}
    if database:
        params["database"] = database
    r = await client.post(CLICKHOUSE_HOST, params=params, auth=_auth_tuple())
    r.raise_for_status()


async def _fetch_json(client: httpx.AsyncClient, sql: str, *, database: str | None = None) -> Dict[str, Any]:
    params = {"query": sql, "default_format": "JSON"}
    if database:
        params["database"] = database
    r = await client.post(CLICKHOUSE_HOST, params=params, auth=_auth_tuple())
    r.raise_for_status()
    return r.json()


async def ensure_migrations_store() -> None:
    """Создаёт служебную таблицу учёта применённых миграций."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE}(
            version String,
            applied_at DateTime
        ) ENGINE = MergeTree() ORDER BY (applied_at)
        """
        await _exec_sql(client, sql, database=CLICKHOUSE_DB)


async def list_applied_versions() -> List[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        sql = f"SELECT version FROM {MIGRATIONS_TABLE} ORDER BY version"
        data = await _fetch_json(client, sql, database=CLICKHOUSE_DB)
        return [row["version"] for row in data.get("data", [])]


def list_files_versions() -> List[str]:
    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    return [os.path.basename(p) for p in files]


def read_migration_sql(version_filename: str) -> str:
    path = os.path.join(MIGRATIONS_DIR, version_filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def apply_migration(version_filename: str) -> None:
    sql = read_migration_sql(version_filename)
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # экранируем одинарные кавычки, чтобы не ронять SQL
    safe_ver = version_filename.replace("'", "''")

    applied_sql = (
        f"INSERT INTO {MIGRATIONS_TABLE} (version, applied_at) "
        f"VALUES ('{safe_ver}', toDateTime('{ts}'))"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        await _exec_sql(client, sql, database=CLICKHOUSE_DB)
        await _exec_sql(client, applied_sql, database=CLICKHOUSE_DB)


async def run_migrations() -> Dict[str, Any]:
    """Запускает все не применённые миграции, возвращает отчёт."""
    await ensure_migrations_store()
    applied = set(await list_applied_versions())
    all_versions = list_files_versions()
    to_apply = [v for v in all_versions if v not in applied]
    applied_now: List[str] = []

    for ver in to_apply:
        await apply_migration(ver)
        applied_now.append(ver)

    return {
        "ok": True,
        "applied_now": applied_now,
        "already_applied": sorted(list(applied)),
        "pending": [v for v in all_versions if v not in applied and v not in applied_now],
        "all": all_versions,
    }


async def migrations_status() -> Dict[str, Any]:
    await ensure_migrations_store()
    applied = set(await list_applied_versions())
    all_versions = list_files_versions()
    pending = [v for v in all_versions if v not in applied]
    return {"ok": True, "applied": sorted(list(applied)), "pending": pending, "all": all_versions}
