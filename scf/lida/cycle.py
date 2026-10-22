ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import time
from typing import Any

from scf.common.audit import emit

_percept_buffer: list[dict] = []
_codelets: list[dict] = []
_action_buffer: list[dict] = []

CYCLE_PHASES = ["perception", "understanding", "attention", "action_selection", "action_execution"]


def perceive(stimulus: dict[str, Any]) -> dict[str, Any]:
    ts = int(time.time())
    percept = {
        "ts": ts,
        "stimulus": stimulus,
        "activation": float(stimulus.get("salience", 0.5)),
    }
    _percept_buffer.append(percept)
    emit("LIDA_PERCEIVE", "lida", f"activation={percept['activation']:.4f}")
    return percept


def run_codelets(percepts: list[dict]) -> list[dict]:
    results = []
    for p in percepts:
        codelet = {
            "ts": int(time.time()),
            "percept_activation": p["activation"],
            "coalition_strength": p["activation"] * 0.9,
            "phase": "attention",
        }
        _codelets.append(codelet)
        results.append(codelet)
    emit("LIDA_CODELETS", "lida", f"coalitions={len(results)}")
    return results


def select_action(coalitions: list[dict]) -> dict[str, Any]:
    if not coalitions:
        emit("LIDA_NO_ACTION", "lida")
        return {"action": "IDLE", "strength": 0.0}
    best = max(coalitions, key=lambda c: c.get("coalition_strength", 0.0))
    action = {
        "ts": int(time.time()),
        "action": "RESPOND",
        "strength": best["coalition_strength"],
        "phase": "action_execution",
    }
    _action_buffer.append(action)
    emit("LIDA_ACTION_SELECTED", "lida", f"strength={action['strength']:.4f}")
    return action


def run_full_cycle(stimulus: dict[str, Any]) -> dict[str, Any]:
    percept = perceive(stimulus)
    coalitions = run_codelets([percept])
    action = select_action(coalitions)
    return {
        "percept": percept,
        "coalitions": coalitions,
        "action": action,
        "phases_completed": CYCLE_PHASES,
    }
