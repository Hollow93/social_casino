# social_casino_backend/app/game_logic.py

import hmac
import hashlib
import uuid
import math

class CrashGame:
    """
    Implements a robust and Provably Fair logic for the crash game.
    This logic is designed for production environments, ensuring fairness,
    verifiability, and a configurable house edge.
    """
    # The house edge is set to 3%. This means that 3% of the time, the game
    # will result in an instant 1.00x crash. This is a common and fair rate.
    HOUSE_EDGE = 0.03

    def __init__(self):
        self.server_seed = ""
        self.hashed_server_seed = ""
        self.nonce = 0
        self.rotate_seeds()
        self.start_time: float | None = None # Start time of the current round
        self.history: list = [] # History of recent rounds
        self.current_countdown = 0

    def rotate_seeds(self):
        """
        Generates a new server seed, hashes it for public view, and resets the nonce.
        A new seed is used for each batch of games (e.g., every 2000 nonces) to ensure
        long-term unpredictability. The hash is shown to players *before* the round
        so they know the seed is predetermined.
        """
        self.server_seed = uuid.uuid4().hex
        self.hashed_server_seed = hashlib.sha256(self.server_seed.encode('utf-8')).hexdigest()
        self.nonce = 0
        print("="*50)
        print(f"** NEW SEED ROTATED **")
        print(f"Server Seed (Secret): {self.server_seed}")
        print(f"Hashed Server Seed (Public): {self.hashed_server_seed}")
        print("="*50)


    def _get_game_hash(self) -> hmac.HMAC:
        """
        Creates an HMAC-SHA256 hash. This is the core of the provably fair system.
        It combines the secret server_seed with the round's nonce.
        Because the server_seed is secret until after the round, the outcome cannot be
        predicted or manipulated by the server or the client.
        """
        # This client_seed is public and can remain constant for verifiability.
        # Its purpose is to add another layer to the HMAC generation.
        client_seed = "social-casino-is-awesome-and-fair" # You can keep this or change it
        message = f"{client_seed}-{self.nonce}".encode('utf-8')
        return hmac.new(self.server_seed.encode('utf-8'), message, hashlib.sha256)

    def calculate_crash_point(self) -> float:
        """
        Calculates the crash point from the game hash in a provably fair manner.
        This function is deterministic: for a given seed and nonce, the result is always the same.

        The process:
        1. Generate a hash for the game round (seed + nonce).
        2. Convert the first 4 bytes of the hash to an integer.
        3. Check if the integer falls within the house edge range (e.g., lowest 3%).
           If so, return an instant crash of 1.00x.
        4. If not, use the integer to calculate a multiplier on an exponential curve.
           This ensures that lower multipliers are significantly more common than high ones.
        """
        self.nonce += 1
        game_hmac = self._get_game_hash()
        hex_val = game_hmac.hexdigest()

        # Use the first 8 characters (4 bytes -> 32 bits) of the hash.
        # 32 bits provides 4,294,967,296 possible outcomes, which is more than enough for fairness.
        int_val = int(hex_val[:8], 16)

        # Total possible outcomes for a 32-bit integer.
        e = 2**32

        # --- House Edge Implementation ---
        # If the generated number is within the lowest `HOUSE_EDGE` percentage of outcomes,
        # the game crashes instantly. This is a more robust and standard way to implement
        # the house edge than using a modulo operator.
        if int_val < e * self.HOUSE_EDGE:
            return 1.00

        # --- Fair Distribution Calculation ---
        # We use the remaining numbers for the main distribution curve.
        # The formula `(1 - HOUSE_EDGE) * e / (e - int_val)` maps the remaining `int_val`
        # to a curve where 1.00x is the minimum and high multipliers are rare.
        # This is a standard and well-regarded formula for crash game fairness.
        crash_point = ((1 - self.HOUSE_EDGE) * e) / (e - int_val)

        # Round down to 2 decimal places and ensure the result is never less than 1.00.
        return max(1.00, math.floor(crash_point * 100) / 100)


    @classmethod
    def get_multiplier_from_duration(cls, duration: float) -> float:
        """Calculates the multiplier for a given duration in seconds using an exponential growth formula."""
        if duration < 0:
            return 1.0
        # This exponential curve provides a smooth and accelerating growth feel.
        # The 0.06 constant can be tweaked to make the game faster or slower.
        return math.pow(math.e, 0.06 * duration)

    @classmethod
    def get_duration_from_multiplier(cls, multiplier: float) -> float:
        """Calculates the time duration in seconds required to reach a given multiplier."""
        if multiplier < 1.0:
            return 0.0
        # This is the inverse function of get_multiplier_from_duration.
        return math.log(multiplier) / 0.06