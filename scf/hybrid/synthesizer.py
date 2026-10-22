ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import time
from typing import Any

from scf.common.audit import emit

THEORY_WEIGHTS = {
    "iit": 0.35,
    "gwt": 0.25,
    "lida": 0.20,
    "ncc": 0.20,
}


def normalize_iit(iit_result: dict) -> float:
    phi = iit_result.get("phi", 0.0)
    return min(phi / 4.0, 1.0)


def normalize_gwt(gwt_result: dict) -> float:
    salience = gwt_result.get("salience", 0.0)
    return min(float(salience), 1.0)


def normalize_lida(lida_result: dict) -> float:
    action = lida_result.get("action", {})
    return min(float(action.get("strength", 0.0)), 1.0)


def normalize_ncc(ncc_result: dict) -> float:
    return min(float(ncc_result.get("ncc_index", 0.0)), 1.0)


def synthesize(
    iit_result: dict[str, Any],
    gwt_result: dict[str, Any],
    lida_result: dict[str, Any],
    ncc_result: dict[str, Any],
) -> dict[str, Any]:
    scores = {
        "iit": normalize_iit(iit_result),
        "gwt": normalize_gwt(gwt_result),
        "lida": normalize_lida(lida_result),
        "ncc": normalize_ncc(ncc_result),
    }

    composite = sum(scores[t] * THEORY_WEIGHTS[t] for t in THEORY_WEIGHTS)

    # FIX #7: bottom label normalised to LOW_AWARENESS/UNCONSCIOUS to match gate + audit strings
    if composite >= 0.75:
        level = "FULL_CONSCIOUSNESS"
    elif composite >= 0.50:
        level = "HIGH_AWARENESS"
    elif composite >= 0.25:
        level = "PARTIAL_AWARENESS"
    elif composite >= 0.10:
        level = "LOW_AWARENESS"
    else:
        level = "UNCONSCIOUS"

    emit("HYBRID_SYNTHESIS", "hybrid", f"composite={composite:.4f} level={level}")

    return {
        "ts": int(time.time()),
        "scores": scores,
        "weights": THEORY_WEIGHTS,
        "composite": composite,
        "consciousness_level": level,
        "theory_breakdown": {
            t: {"raw": scores[t], "weighted": scores[t] * THEORY_WEIGHTS[t]}
            for t in THEORY_WEIGHTS
        },
    }
