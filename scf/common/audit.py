TIMESTAMP_SKEW = 120
ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import hashlib
import time
from typing import Any

_chain: list[dict] = []


def _sha3(data: str) -> str:
    return hashlib.sha3_512(data.encode()).hexdigest()


def emit(event: str, module: str, detail: Any = None) -> str:
    prev = _chain[-1]["hash"] if _chain else "GENESIS"
    entry = {
        "seq": len(_chain),
        "ts": int(time.time()),
        "module": module,
        "event": event,
        "detail": str(detail) if detail is not None else "",
        "prev": prev,
    }
    entry["hash"] = _sha3(f"{prev}^@^{entry['seq']}^@^{entry['ts']}^@^{module}^@^{event}^@^{entry['detail']}")
    _chain.append(entry)
    return entry["hash"]


def tail(n: int = 20) -> list[dict]:
    return _chain[-n:]


def verify_chain() -> bool:
    for i, entry in enumerate(_chain):
        prev = _chain[i - 1]["hash"] if i > 0 else "GENESIS"
        expected = f"{prev}^@^{entry['seq']}^@^{entry['ts']}^@^{entry['module']}^@^{entry['event']}^@^{entry['detail']}"
        if hashlib.sha3_512(expected.encode()).hexdigest() != entry["hash"]:
            return False
    return True
