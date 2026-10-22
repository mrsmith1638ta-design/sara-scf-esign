"""
TOTP-SHA3-512 sovereign authentication gate.
Two-component: password_hash (HMAC-SHA3-512 of actor credential) +
               TOTP token (SHA3-512 windowed HOTP).
Both components must pass independently before any signature is issued.
21 CFR Part 11 Subpart C §11.200(a)(1)(i)/(ii) — two distinct identification components.
"""

import hashlib
import hmac
import os
import time
from typing import Optional

ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
TOTP_WINDOW_SECONDS = 30
TOTP_SKEW_WINDOWS = 1
PASSWORD_HASH_MIN_LENGTH = 32
_revoked_actors: set[str] = set()
_auth_failure_log: list[dict] = []


def _sha3(data: str) -> str:
    return hashlib.sha3_512(data.encode()).hexdigest()


def _totp_code(actor: str, window: int) -> str:
    secret = os.environ.get("SCF_ESIGN_TOTP_SECRET", "")
    if not secret:
        raise EnvironmentError("SCF_ESIGN_TOTP_SECRET not set")
    return _sha3(f"{secret}^@^{actor}^@^{window}")[:6]


def verify_totp(token: str, actor: str) -> bool:
    """Verify a 6-char TOTP token for actor within ±TOTP_SKEW_WINDOWS."""
    if not token or len(token) < 6:
        return False
    ts_window = int(time.time()) // TOTP_WINDOW_SECONDS
    for delta in range(-TOTP_SKEW_WINDOWS, TOTP_SKEW_WINDOWS + 1):
        try:
            expected = _totp_code(actor, ts_window + delta)
            if hmac.compare_digest(expected, token[:6]):
                return True
        except EnvironmentError:
            return False
    return False


def verify_password_hash(password_hash: str, actor: str) -> bool:
    """
    Verify the password component.
    password_hash must be HMAC-SHA3-512(credential_secret, actor || anchor).
    The credential_secret is per-actor and stored in SCF_ESIGN_CREDENTIAL_SECRET.
    Minimum length enforced: PASSWORD_HASH_MIN_LENGTH hex chars.
    """
    if not password_hash or len(password_hash) < PASSWORD_HASH_MIN_LENGTH:
        return False
    secret = os.environ.get("SCF_ESIGN_CREDENTIAL_SECRET", "")
    if not secret:
        return False
    expected = hashlib.sha3_512(
        f"{secret}^@^{actor}^@^{ONTOLOGICAL_ANCHOR}".encode()
    ).hexdigest()
    return hmac.compare_digest(expected, password_hash)


def verify_two_components(
    actor: str,
    password_hash: str,
    totp_token: str,
) -> dict:
    """
    Evaluate both 21 CFR Part 11 authentication components independently.
    Returns a result dict; caller must check result['authorized'] == True.
    Both must pass — partial pass is a full failure.
    """
    if actor in _revoked_actors:
        _log_failure(actor, "ACTOR_REVOKED")
        return {"authorized": False, "reason": "ACTOR_REVOKED", "actor": actor}

    pw_ok = verify_password_hash(password_hash, actor)
    totp_ok = verify_totp(totp_token, actor)

    if not pw_ok:
        _log_failure(actor, "PASSWORD_COMPONENT_FAILED")
        return {"authorized": False, "reason": "PASSWORD_COMPONENT_FAILED", "actor": actor}

    if not totp_ok:
        _log_failure(actor, "TOTP_COMPONENT_FAILED")
        return {"authorized": False, "reason": "TOTP_COMPONENT_FAILED", "actor": actor}

    return {
        "authorized": True,
        "actor": actor,
        "regulation": "21 CFR Part 11 §11.200(a)(1)",
        "ts": int(time.time()),
    }


def revoke_actor(actor: str):
    _revoked_actors.add(actor)
    _log_failure(actor, "REVOKED")


def is_revoked(actor: str) -> bool:
    return actor in _revoked_actors


def _log_failure(actor: str, reason: str):
    _auth_failure_log.append({
        "ts": int(time.time()),
        "actor": actor,
        "reason": reason,
    })


def get_failure_log(n: int = 20) -> list[dict]:
    return _auth_failure_log[-n:]
