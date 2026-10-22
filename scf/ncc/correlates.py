ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import math
import time
from typing import Any

from scf.common.audit import emit

NCC_MARKERS = [
    "recurrent_processing",
    "late_cortical_amplification",
    "global_ignition",
    "sustained_gamma_oscillation",
    "thalamo_cortical_loop",
]


def score_marker(marker: str, signal_strength: float) -> dict[str, Any]:
    threshold = 0.6
    active = signal_strength >= threshold
    emit("NCC_MARKER", "ncc", f"{marker}={'ACTIVE' if active else 'INACTIVE'} sig={signal_strength:.4f}")
    return {
        "marker": marker,
        "signal_strength": signal_strength,
        "active": active,
        "threshold": threshold,
    }


def compute_ncc_index(signals: dict[str, float]) -> dict[str, Any]:
    results = []
    for marker in NCC_MARKERS:
        sig = signals.get(marker, 0.0)
        results.append(score_marker(marker, sig))

    active_count = sum(1 for r in results if r["active"])
    ncc_index = active_count / len(NCC_MARKERS)

    consciousness_state = "CONSCIOUS" if ncc_index >= 0.6 else ("SUBCONSCIOUS" if ncc_index >= 0.3 else "UNCONSCIOUS")
    emit("NCC_INDEX", "ncc", f"index={ncc_index:.4f} state={consciousness_state}")

    return {
        "ts": int(time.time()),
        "markers": results,
        "active_count": active_count,
        "ncc_index": ncc_index,
        "consciousness_state": consciousness_state,
    }


def integrate_with_iit(phi: float, ncc_index: float) -> dict[str, Any]:
    combined = (phi / (phi + 4.0)) * 0.5 + ncc_index * 0.5
    emit("NCC_IIT_INTEGRATE", "ncc", f"phi={phi:.4f} ncc={ncc_index:.4f} combined={combined:.4f}")
    return {
        "phi": phi,
        "ncc_index": ncc_index,
        "combined_score": combined,
        "assessment": "HIGH" if combined >= 0.6 else ("MEDIUM" if combined >= 0.3 else "LOW"),
    }
