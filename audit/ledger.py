"""
SCF-Esign audit ledger.
SHA3-512 hash-chained append-only log covering both SCF assessments
and e-signature lifecycle events.
"""

import hashlib
import hmac
import json
import os
import time
import uuid

ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"

_chain: list[dict] = []


def _sha3(data: str) -> str:
    return hashlib.sha3_512(data.encode()).hexdigest()


def _hmac_sign(data: bytes) -> str:
    # FIX #4: unified secret — SCF_ESIGN_AUDIT_HMAC_SECRET removed; use SCF_ESIGN_HMAC_SECRET
    raw = os.environ.get("SCF_ESIGN_HMAC_SECRET") or os.environ.get("SCF_HMAC_SECRET", "")
    if not raw:
        raise RuntimeError("SCF_ESIGN_HMAC_SECRET must be set for audit ledger HMAC")
    return hmac.new(raw.encode(), data, hashlib.sha3_512).hexdigest()


def emit(event: str, module: str, detail: object = None) -> str:
    prev = _chain[-1]["entry_hash"] if _chain else "GENESIS"
    ts = int(time.time())
    entry = {
        "entry_id": str(uuid.uuid4()),
        "seq": len(_chain),
        "ts": ts,
        "module": module,
        "event": event,
        "detail": str(detail) if detail is not None else "",
        "prev_hash": prev,
        "anchor": ONTOLOGICAL_ANCHOR,
    }
    entry["entry_hash"] = _sha3(json.dumps(entry, sort_keys=True))
    entry["chain_hmac"] = _hmac_sign(entry["entry_hash"].encode())
    _chain.append(entry)
    return entry["entry_hash"]


def tail(n: int = 20) -> list[dict]:
    return _chain[-n:]


def verify_chain() -> dict:
    for i, entry in enumerate(_chain):
        prev = _chain[i - 1]["entry_hash"] if i > 0 else "GENESIS"
        if entry.get("prev_hash") != prev:
            return {"valid": False, "broken_at_seq": i, "chain_length": len(_chain)}
    return {"valid": True, "chain_length": len(_chain), "ts": int(time.time())}
