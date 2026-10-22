import hashlib
import hmac
import os
import time
from typing import Optional

ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
TIMESTAMP_SKEW_SECONDS = 120
FORBIDDEN_ALGOS = {"rsa", "aes", "sha256", "sha512", "md5"}


def get_hmac_secret() -> bytes:
    # FIX #5: use .get() on fallback to avoid KeyError crash at startup
    raw = os.environ.get("SCF_ESIGN_HMAC_SECRET") or os.environ.get("SCF_HMAC_SECRET", "")
    if not raw:
        raise RuntimeError("SCF_ESIGN_HMAC_SECRET (or SCF_HMAC_SECRET) must be set")
    return raw.encode()


def sha3_512(data: bytes) -> str:
    return hashlib.sha3_512(data).hexdigest()


def hmac_sha512(key: bytes, data: bytes) -> str:
    return hmac.new(key, data, hashlib.sha3_512).hexdigest()


def build_envelope(module: str, payload: bytes) -> dict:
    ts = str(int(time.time()))
    anchor = ONTOLOGICAL_ANCHOR
    signing_input = f"{anchor}^@^{module}^@^{ts}^@^".encode() + payload
    sig = hmac_sha512(get_hmac_secret(), signing_input)
    return {
        "X-SARA-Module": module,
        "X-SARA-Timestamp": ts,
        "X-SARA-Signature": sig,
        "X-SARA-Anchor": anchor,
    }


def verify_envelope(module: str, timestamp: str, signature: str, payload: bytes) -> bool:
    now = int(time.time())
    ts = int(timestamp)
    if abs(now - ts) > TIMESTAMP_SKEW_SECONDS:
        return False
    anchor = ONTOLOGICAL_ANCHOR
    signing_input = f"{anchor}^@^{module}^@^{timestamp}^@^".encode() + payload
    expected = hmac_sha512(get_hmac_secret(), signing_input)
    return hmac.compare_digest(expected, signature)
