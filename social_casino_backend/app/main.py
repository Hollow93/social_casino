# social_casino_backend/app/main.py

import os
import asyncio
import time
import hashlib
import hmac
import json
import base64
from typing import Tuple, Optional, Dict, Any
from urllib.parse import parse_qsl, unquote

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Body, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime, timedelta

from app.clickhouse_logger import log_event, ensure_clickhouse, ch_status, log_spin, _auth_tuple, CLICKHOUSE_DB, CLICKHOUSE_HOST, CLICKHOUSE_SPINS_TABLE
from app.migrations_runner import run_migrations, migrations_status
from app.ws_manager import WebSocketManager
from app.game_logic import CrashGame
from app.db import init_db, get_or_create_user, update_balance, get_balance

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в окружении контейнера.")
BOT_ID = int(BOT_TOKEN.split(":", 1)[0])

TMA_PUBLIC_KEY_HEX_PROD = "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d"

logger = logging.getLogger("uvicorn.error")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

game = CrashGame()
manager = WebSocketManager(game)

def _sorted_pairs_without(init_data: str, *exclude: str) -> tuple[str, Dict[str, str]]:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    for k in exclude:
        pairs.pop(k, None)
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    return check_string, pairs

def _validate_hash(init_data: str, bot_token: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    all_pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    given_hash = (all_pairs.get("hash") or "").lower()
    if not given_hash:
        return False, None, "missing_hash"

    check_string, data = _sorted_pairs_without(init_data, "hash", "signature")

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if calc_hash != given_hash:
        return False, None, "bad_hash"

    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        return False, None, "bad_auth_date"
    now = int(time.time())
    if not (-60 <= (now - auth_date) <= 86400):
        return False, None, "auth_date_too_old"

    try:
        user_obj = json.loads(data.get("user", "{}"))
    except Exception:
        return False, None, "bad_user_json"
    if not user_obj or "id" not in user_obj:
        return False, None, "missing_user"
    return True, user_obj, "ok_hash"

def _b64url_decode_with_padding(s: str) -> bytes:
    pad = (-len(s)) % 4
    if pad:
        s = s + ("=" * pad)
    return base64.urlsafe_b64decode(s.encode())

def _validate_signature(init_data: str, bot_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    all_pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    signature_b64 = all_pairs.get("signature")
    if not signature_b64:
        return False, None, "missing_signature"

    check_string, data = _sorted_pairs_without(init_data, "hash", "signature")
    message = f"{bot_id}:WebAppData\n{check_string}".encode()

    pubkey = bytes.fromhex(TMA_PUBLIC_KEY_HEX_PROD)
    verify_key = VerifyKey(pubkey)

    try:
        sig = _b64url_decode_with_padding(signature_b64)
    except Exception as e:
        return False, None, f"bad_signature_b64:{e}"

    try:
        verify_key.verify(message, sig)
    except BadSignatureError:
        return False, None, "bad_signature"

    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        return False, None, "bad_auth_date"
    now = int(time.time())
    if not (-60 <= (now - auth_date) <= 86400):
        return False, None, "auth_date_too_old"

    try:
        user_obj = json.loads(data.get("user", "{}"))
    except Exception:
        return False, None, "bad_user_json"
    if not user_obj or "id" not in user_obj:
        return False, None, "missing_user"

    return True, user_obj, "ok_signature"

def validate_init_data(init_data: str, bot_token: str, bot_id: Optional[str]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    ok, user, reason = _validate_hash(init_data, bot_token)
    if ok:
        return ok, user, reason
    if bot_id:
        return _validate_signature(init_data, bot_id)
    return False, None, reason

async def game_loop():
    while True:
        print("\n--- New Round: Preparation ---")
        game.start_time = None
        manager.prepare_new_round()

        if game.nonce >= 2000:
            game.rotate_seeds()

        print("--- Waiting for bets... ---")
        history_data = [{"multiplier": item["multiplier"]} for item in game.history]
        wait_time = 10
        for i in range(wait_time, 0, -1):
            game.current_countdown = i
            await manager.broadcast({"type": "waiting", "data": {"countdown": i, "history": history_data, "hashed_server_seed": game.hashed_server_seed}})
            await asyncio.sleep(1)
        game.current_countdown = 0

        await manager.activate_auto_bets()

        crash_point = game.calculate_crash_point()
        game.start_time = time.time()
        manager.activate_bets()
        print(f"--- Round Started! Nonce: {game.nonce}, Crashing at {crash_point:.2f}x ---")

        await manager.broadcast({"type": "round_start", "data": {"startTime": game.start_time}})

        crash_duration = game.get_duration_from_multiplier(crash_point)
        await asyncio.sleep(crash_duration)

        print(f"--- Crashed at {crash_point:.2f}x ---")
        round_info = {"multiplier": crash_point, "server_seed": game.server_seed, "hashed_server_seed": game.hashed_server_seed, "nonce": game.nonce}
        game.history.insert(0, round_info)
        if len(game.history) > 30:
            game.history.pop()

        history_data_new = [{"multiplier": item["multiplier"]} for item in game.history]
        await manager.broadcast({"type": "round_end", "data": {"crashPoint": crash_point, "history": history_data_new, "roundInfo": round_info}})
        await manager.resolve_bets(crash_point)

        print("--- Resolving bets and waiting for next round... ---")
        await asyncio.sleep(5)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    init_data_str: Optional[str] = None
    user_obj: Optional[Dict[str, Any]] = None

    try:
        q_init = websocket.query_params.get("initData")
        if q_init:
            ok, user_obj, reason = validate_init_data(q_init, BOT_TOKEN, BOT_ID)
            logger.info(f"WS query initData validation: {reason}")
            if ok and user_obj:
                init_data_str = q_init
    except Exception as e:
        logger.warning(f"WS query parse error: {e}")

    if not init_data_str:
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            try:
                payload = json.loads(first) if first else {}
            except json.JSONDecodeError:
                payload = {}
            if payload.get("action") == "handshake" and "init_data" in payload:
                candidate = payload["init_data"]
                ok, user_obj, reason = validate_init_data(candidate, BOT_TOKEN, BOT_ID)
                logger.info(f"WS handshake validation: {reason}")
                if ok and user_obj:
                    init_data_str = candidate
        except asyncio.TimeoutError:
            logger.warning("WS handshake timeout")
        except Exception as e:
            logger.exception(f"WS handshake receive error: {e}")

    if not init_data_str or not user_obj:
        logger.warning("Invalid initData. Closing connection.")
        await websocket.close(code=1008, reason="Invalid credentials")
        return

    user_id = str(user_obj["id"])
    username = user_obj.get("username")

    try:
        parsed_qsl = dict(parse_qsl(unquote(init_data_str)))
        user_source = json.loads(parsed_qsl.get("user", "{}")).get("start_param")
    except Exception:
        user_source = None

    try:
        asyncio.create_task(log_event(event_type="user_connect", user_id=int(user_id), payload={"username": username}, user_source=user_source))
    except Exception:
        pass

    get_or_create_user(int(user_id), username)

    await manager.connect(websocket, user_id)
    logger.info(f"User {user_id} ({username}) connected.")

    try:
        history_data = [{"multiplier": item["multiplier"]} for item in game.history]
        if game.start_time:
            initial_message = {"type": "round_start", "data": {"startTime": game.start_time, "history": history_data, "is_initial_sync": True}}
        else:
            initial_message = {"type": "waiting", "data": {"countdown": game.current_countdown, "history": history_data, "hashed_server_seed": game.hashed_server_seed, "is_initial_sync": True}}
        await websocket.send_json(initial_message)

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "place_bet":
                logger.info(f"User {user_id} placing bet: {data}")
                await manager.add_bet(
                    user_id=user_id,
                    panel_id=int(data.get("panelId")),
                    bet_data={
                        "amount": float(data.get("amount")),
                        "autoCashoutAt": (float(data.get("autoCashoutAt")) if data.get("autoCashoutAt") else None),
                    },
                )
            elif msg_type == "cash_out":
                logger.info(f"User {user_id} cashing out: {data}")
                await manager.cash_out_user(user_id=user_id, panel_id=int(data.get("panelId")))
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"User {user_id} disconnected.")
    except Exception as e:
        logger.exception(f"WS error for user {user_id}: {e}")
        manager.disconnect(user_id)

@app.post("/create-star-invoice")
async def create_star_invoice(data: dict = Body(...)):
    user_id = data.get("user_id")
    amount = data.get("amount")
    if not user_id or not amount:
        return {"ok": False, "error": "missing_params"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink"
    payload = {
        "title": "Purchase Crystals",
        "description": f"A pack of {amount} crystals for the game.",
        "payload": f"recharge-{user_id}-{int(time.time())}",
        "currency": "XTR",
        "prices": json.dumps([{"label": f"{amount} crystals", "amount": amount}]),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, data=payload)
    if resp.status_code == 200:
        return {"ok": True, "invoice_link": resp.json().get("result")}
    logger.error(f"Error creating invoice: {resp.text}")
    return {"ok": False, "error": "create_invoice_failed"}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    logger.info(f"Received webhook: {data}")

    if "pre_checkout_query" in data:
        query_id = data["pre_checkout_query"]["id"]
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery"
        payload = {"pre_checkout_query_id": query_id, "ok": True}
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(url, json=payload)
        logger.info(f"Answered pre_checkout_query {query_id}")
        return {"status": "ok"}

    if "message" in data and "successful_payment" in data["message"]:
        payment_info = data["message"]["successful_payment"]
        user_id = data["message"]["from"]["id"]
        amount_paid = payment_info["total_amount"]

        current_balance = get_balance(user_id)
        is_ftd = current_balance == 0

        try:
            asyncio.create_task(log_event(
                event_type="successful_payment",
                user_id=user_id,
                payload={"amount": amount_paid, "currency": payment_info.get("currency", "XTR"), "is_ftd": is_ftd},
                user_source=None,
            ))
        except Exception:
            pass

        # дополнительно лог в spins: deposit
        try:
            asyncio.create_task(log_spin(
                user_id=str(user_id),
                event_type="deposit",
                amount=float(amount_paid),
                multiplier=1.0,
            ))
        except Exception:
            pass

        new_balance = update_balance(user_id, float(amount_paid), op="inc")
        await manager.send_to_user(str(user_id), {"type": "balance_update", "data": {"balance": new_balance}})
        logger.info(f"User {user_id} successfully paid {amount_paid}. New balance: {new_balance}")

    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ---- Админ: ClickHouse/миграции/метрики ----

@app.get("/admin/migrations/status")
async def admin_migrations_status():
    return await migrations_status()

@app.post("/admin/migrations/run")
async def admin_migrations_run():
    return await run_migrations()

@app.get("/admin/ensure_clickhouse")
async def admin_ensure_clickhouse():
    return await ensure_clickhouse()

@app.get("/admin/ch_status")
async def admin_ch_status():
    return await ch_status()

@app.get("/admin/metrics/summary")
async def metrics_summary(hours: int = Query(24, ge=1, le=720)):
    await ensure_clickhouse()
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
    WITH toDateTime('{since}') AS since
    SELECT
      sumIf(amount, event_type = 'deposit')   AS deposit_sum,
      countIf(event_type = 'bet_success')     AS bet_success_cnt,
      countIf(event_type = 'bet_fail')        AS bet_fail_cnt,
      sumIf(amount, event_type = 'win')       AS win_sum,
      sumIf(amount, event_type = 'loss')      AS loss_sum
    FROM {CLICKHOUSE_SPINS_TABLE}
    WHERE timestamp >= since
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(CLICKHOUSE_HOST, params={"query": sql, "database": CLICKHOUSE_DB, "default_format": "JSON"}, auth=_auth_tuple())
        r.raise_for_status()
        data = r.json()
    rows = data.get("data", [])
    result = rows[0] if rows else {}
    result["net"] = float(result.get("win_sum", 0) - result.get("deposit_sum", 0))
    return result

@app.get("/admin/metrics/by-hour")
async def metrics_by_hour(hours: int = Query(24, ge=1, le=720)):
    await ensure_clickhouse()
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
    WITH toDateTime('{since}') AS since
    SELECT
      toStartOfHour(timestamp) AS hour,
      sumIf(amount, event_type = 'deposit') AS deposit_sum,
      countIf(event_type = 'bet_success')    AS bet_success_cnt,
      countIf(event_type = 'bet_fail')       AS bet_fail_cnt,
      sumIf(amount, event_type = 'win')      AS win_sum,
      sumIf(amount, event_type = 'loss')     AS loss_sum
    FROM {CLICKHOUSE_SPINS_TABLE}
    WHERE timestamp >= since
    GROUP BY hour
    ORDER BY hour ASC
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(CLICKHOUSE_HOST, params={"query": sql, "database": CLICKHOUSE_DB, "default_format": "JSON"}, auth=_auth_tuple())
        r.raise_for_status()
        data = r.json()
    return data.get("data", [])

@app.on_event("startup")
async def on_startup():
    init_db()
    # 1) миграции
    try:
        report = await run_migrations()
        logger.info(f"[MIGRATIONS] applied_now={report.get('applied_now')}, pending={report.get('pending')}")
    except Exception as e:
        logger.warning(f"[MIGRATIONS] failed: {e}")
    # 2) CH доступность/детект payload
    try:
        st = await ensure_clickhouse()
        logger.info(f"[CH] reachable={st.get('reachable')} payload_type={st.get('payload_type')} err={st.get('error')}")
    except Exception as e:
        logger.warning(f"ensure_clickhouse failed: {e}")
    asyncio.create_task(game_loop())
