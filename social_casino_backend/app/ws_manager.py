# social_casino_2.0/social_casino_backend/app/ws_manager.py

import time
from fastapi import WebSocket
from app.game_logic import CrashGame
from app.db import get_balance, update_balance # <--- ИМПОРТ
from app.clickhouse_logger import log_event

class WebSocketManager:
    """Manages WebSocket connections, user bets, and broadcasting."""

    def __init__(self, game: CrashGame):
        self.active_connections: dict[str, WebSocket] = {}
        self.bets: dict[str, list] = {}
        self.game = game

    async def connect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id] = websocket

        # Отправляем актуальный баланс из БД при подключении
        balance = get_balance(int(user_id))
        await self.send_to_user(user_id, {"type": "balance_update", "data": {"balance": balance}})


    def disconnect(self, user_id: str):
        """Removes a user's connection and cleans up their data."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.bets:
            del self.bets[user_id]
        print(f"Cleaned up data for user {user_id}")


    async def send_to_user(self, user_id: str, message: dict):
        """Sends a JSON message to a specific user."""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json(message)
            except Exception as e:
                print(f"Failed to send message to {user_id}: {e}. Disconnecting.")
                self.disconnect(user_id)

    async def broadcast(self, message: dict):
        """Sends a JSON message to all connected users."""
        for user_id, connection in list(self.active_connections.items()):
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Failed to broadcast to {user_id}: {e}. Disconnecting.")
                self.disconnect(user_id)

    def prepare_new_round(self):
        """Clears all bets for the new round. Called at the start of each round."""
        for user_id, user_bets in self.bets.items():
            self.bets[user_id] = [
                self.bets[user_id][0] if user_bets[0] and user_bets[0].get('autoBet') else None,
                self.bets[user_id][1] if user_bets[1] and user_bets[1].get('autoBet') else None,
            ]


    async def add_bet(self, user_id: str, panel_id: int, bet_data: dict):
        """Adds a user's bet for the upcoming round."""
        if self.game.start_time is not None:
            await self.send_to_user(user_id, {"type": "bet_error", "data": {"panelId": panel_id, "message": "Too late to bet."}})
            return

        if user_id not in self.bets:
            self.bets[user_id] = [None, None]

        if self.bets[user_id][panel_id] is not None:
            await self.send_to_user(user_id, {"type": "bet_error", "data": {"panelId": panel_id, "message": "Bet for this panel already placed."}})
            return

        amount_to_bet = bet_data["amount"]
        current_balance = get_balance(int(user_id))

        # --- Логирование попытки ставки ---
        log_event(int(user_id), "bet_placed", {
            "amount": amount_to_bet,
            "panel_id": panel_id,
            "current_balance": current_balance,
            "auto_cashout_at": bet_data.get("autoCashoutAt")
        })
        # -----------------------------------

        if current_balance < amount_to_bet:
            # --- Логирование ошибки ставки ---
            log_event(int(user_id), "bet_error_insufficient_funds", {
                "amount_bet": amount_to_bet,
                "balance": current_balance
            })
            # ---------------------------------
            await self.send_to_user(user_id, {"type": "bet_error", "data": {"panelId": panel_id, "message": "Not enough crystals."}})
            return

        new_balance = update_balance(int(user_id), -amount_to_bet, is_delta=True)

        self.bets[user_id][panel_id] = {
            "amount": amount_to_bet,
            "autoCashoutAt": bet_data["autoCashoutAt"],
            "status": "placed",
            "winAmount": 0,
            "cashedOutAt": None
        }

        await self.send_to_user(user_id, {"type": "bet_confirm", "data": {"panelId": panel_id}})
        await self.send_to_user(user_id, {"type": "balance_update", "data": {"balance": new_balance}})

    def activate_bets(self):
        """Activates all 'placed' bets at the start of the round."""
        for user_id, user_bets in self.bets.items():
            for bet in user_bets:
                if bet and bet.get("status") == "placed":
                    bet["status"] = "active"

    async def cash_out_user(self, user_id: str, panel_id: int):
        """Processes a manual cash-out request from a user."""
        if user_id not in self.bets or self.bets[user_id][panel_id] is None:
            return

        bet = self.bets[user_id][panel_id]

        if bet.get("status") == "active" and self.game.start_time is not None:
            elapsed = time.time() - self.game.start_time
            current_multiplier = self.game.get_multiplier_from_duration(elapsed)
            win_amount = bet["amount"] * current_multiplier

            bet["status"] = "cashed_out"
            bet["winAmount"] = win_amount
            bet["cashedOutAt"] = current_multiplier

            # --- Логирование выигрыша (ручной кэшаут) ---
            log_event(int(user_id), "bet_win", {
                "bet_amount": bet["amount"],
                "win_amount": win_amount,
                "multiplier": current_multiplier,
                "cashout_type": "manual"
            })
            # ----------------------------------------

            # --- Начисляем выигрыш в БД ---
            new_balance = update_balance(int(user_id), win_amount, is_delta=True)

            await self.send_to_user(user_id, {
                "type": "bet_result",
                "data": {
                    "panelId": panel_id,
                    "winAmount": round(win_amount, 2),
                    "cashedOutAt": round(current_multiplier, 2)
                }
            })
            # Отправляем обновленный баланс
            await self.send_to_user(user_id, {"type": "balance_update", "data": {"balance": new_balance}})


    async def resolve_bets(self, crash_point: float):
        """Resolves the outcome for all active bets at the end of a round."""
        for user_id, user_bets in self.bets.items():
            for i, bet in enumerate(user_bets):
                if bet is None or bet.get("status") != "active":
                    continue

                win_amount = 0
                cashed_at = None

                if bet.get("autoCashoutAt") and bet.get("autoCashoutAt") <= crash_point:
                    win_amount = bet["amount"] * bet["autoCashoutAt"]
                    cashed_at = bet["autoCashoutAt"]
                    bet["status"] = "cashed_out"

                    # --- Логирование выигрыша (авто-кэшаут) ---
                    log_event(int(user_id), "bet_win", {
                        "bet_amount": bet["amount"],
                        "win_amount": win_amount,
                        "multiplier": cashed_at,
                        "cashout_type": "auto"
                    })
                    # ----------------------------------------

                    # --- Начисляем выигрыш в БД ---
                    update_balance(int(user_id), win_amount, is_delta=True)
                else:
                    bet["status"] = "resolved"
                    # --- Логирование проигрыша ---
                    log_event(int(user_id), "bet_loss", {
                        "bet_amount": bet["amount"],
                        "crash_point": crash_point
                    })
                    # ---------------------------

                await self.send_to_user(user_id, {
                    "type": "bet_result",
                    "data": {
                        "panelId": i,
                        "winAmount": round(win_amount, 2),
                        "cashedOutAt": cashed_at
                    }
                })

        # После разрешения всех ставок, отправим всем обновленный баланс
        for user_id in self.active_connections.keys():
             balance = get_balance(int(user_id))
             await self.send_to_user(user_id, {"type": "balance_update", "data": {"balance": balance}})


    async def activate_auto_bets(self):
        for user_id, user_bets in self.bets.items():
            for i, bet in enumerate(user_bets):
                if bet and bet.get("autoBet"):
                    bet['status'] = 'placed'
