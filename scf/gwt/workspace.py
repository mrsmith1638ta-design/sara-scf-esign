ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import time
from typing import Any

from scf.common.audit import emit

_workspace: dict[str, Any] = {}
_broadcast_log: list[dict] = []

SPECIALIST_MODULES = ["iit", "lida", "ncc", "hybrid", "safety"]


def broadcast(content: dict[str, Any], source: str) -> dict[str, Any]:
    ts = int(time.time())
    entry = {
        "ts": ts,
        "source": source,
        "content": content,
        "recipients": [m for m in SPECIALIST_MODULES if m != source],
    }
    _workspace.update(content)
    _workspace["last_broadcast_ts"] = ts
    _workspace["last_broadcast_source"] = source
    _broadcast_log.append(entry)
    emit("GWT_BROADCAST", "gwt", f"source={source} keys={list(content.keys())}")
    return entry


def read_workspace(key: str = None) -> Any:
    if key:
        return _workspace.get(key)
    return dict(_workspace)


def competition(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        emit("GWT_COMPETITION_EMPTY", "gwt")
        return {}
    winner = max(candidates, key=lambda c: c.get("salience", 0.0))
    emit("GWT_COMPETITION_WON", "gwt", f"winner_salience={winner.get('salience', 0.0):.4f}")
    broadcast(winner, source="competition")
    return winner


def get_broadcast_log(n: int = 10) -> list[dict]:
    return _broadcast_log[-n:]
