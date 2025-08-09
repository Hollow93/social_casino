# /var/www/skill/triage_webapp_hash.py
import hmac, hashlib, urllib.parse, sys

# 1) ВСТАВЬ СЮДА АКТУАЛЬНЫЙ initData (скопированный из Telegram WebApp DevTools СЕЙЧАС, целиком):
INIT_DATA = r"""query_id=AAHRqv4WAAAAANGq_hZUTyMK&user=%7B%22id%22%3A385788625%2C%22first_name%22%3A%22%D0%92%D0%BB%D0%B0%D0%B4%22%2C%22last_name%22%3A%22%D0%91%D1%8B%D0%BA%D0%BE%D0%BD%D1%8C%22%2C%22username%22%3A%22hollow93%22%2C%22language_code%22%3A%22ru%22%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FSeFb_sXm61UJPOVmOHKwNmUJ6kEGRoTT6vF1MnsYbbE.svg%22%7D&auth_date=1754684724&signature=khs1HuLKQR5qqMw_b0cRuGawudBWH3-UUKpkbNNNPa4sPlcI9N7XsuTJtmv6MW_7jYdKIMCeD2SaysrkojVECA&hash=0bc2e40cfe1d2ad9576140e3051ab2f79de7b2724e40c80c2831772472508cb9"""

# 2) ДВА подозреваемых токена — подставь свои:
TOKENS = {
    "new_8111": "8111352574:AAGC-ax46qx_JEkG1inM375Cz-BXTbc-fPw",  # skill_forge_factory_bot
    "old_7982": "7982108794:AAFaI0j2DRaGxrnwfFiD0TInNdnb1t8X9MQ",  # старый
}

def build_check_string(init_data: str) -> tuple[str, dict]:
    pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    given_hash = (pairs.get("hash") or "").lower()
    pairs.pop("hash", None)
    pairs.pop("signature", None)  # не участвует
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    return check_string, given_hash

def try_calc(label, token, check_string, given_hash):
    sha_secret = hashlib.sha256(token.encode()).digest()
    webapp_secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()

    calc_login = hmac.new(sha_secret, check_string.encode(), hashlib.sha256).hexdigest()
    calc_webapp = hmac.new(webapp_secret, check_string.encode(), hashlib.sha256).hexdigest()

    print(f"\n== {label} ==")
    print(" given: ", given_hash)
    print(" login: ", calc_login, "  (секрет = SHA256(token))")
    print(" webapp:", calc_webapp, "  (секрет = HMAC('WebAppData', token))")
    print(" match_login? ", calc_login == given_hash)
    print(" match_webapp? ", calc_webapp == given_hash)

def main():
    check_string, given_hash = build_check_string(INIT_DATA)
    print("check_string:\n" + check_string)

    for label, token in TOKENS.items():
        try_calc(label, token, check_string, given_hash)

if __name__ == "__main__":
    main()
