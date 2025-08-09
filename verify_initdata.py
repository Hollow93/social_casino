import hmac, hashlib, urllib.parse, time
BOT_TOKEN = "7982108794:AAFaI0j2DRaGxrnwfFiD0TInNdnb1t8X9MQ"   # СТАРЫЙ
INIT_DATA = r"""query_id=AAHRqv4WAAAAANGq_hbTYqzA&user=%7B%22id%22%3A385788625%2C%22first_name%22%3A%22%D0%92%D0%BB%D0%B0%D0%B4%22%2C%22last_name%22%3A%22%D0%91%D1%8B%D0%BA%D0%BE%D0%BD%D1%8C%22%2C%22username%22%3A%22hollow93%22%2C%22language_code%22%3A%22ru%22%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FSeFb_sXm61UJPOVmOHKwNmUJ6kEGRoTT6vF1MnsYbbE.svg%22%7D&auth_date=1754683950&signature=KMHMR3mD0R3Fftw8T82t5pdzuDjhZWiHBKkXJsusi_Ie0fNboYRingQNhRet0NRoo2yplQ5iTeuPNYfQGVW6Cw&hash=a1a372e59f66c9923781dc11640140efc0426ac163a9c95bc4320317fa4d6b7e"""
pairs = dict(urllib.parse.parse_qsl(INIT_DATA, keep_blank_values=True))
given_hash = (pairs.get("hash") or "").lower()
pairs.pop("hash", None); pairs.pop("signature", None)
check_string = "\n".join(f"{k}={v}" for k,v in sorted(pairs.items()))
secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
calc = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
print("OK? ", calc == given_hash)
print("calc", calc)
print("giv ", given_hash)
