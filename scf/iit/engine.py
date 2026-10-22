TIMESTAMP_SKEW = 120
ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import itertools
import math
from typing import Any

from scf.common.audit import emit


def _entropy(probs: list[float]) -> float:
    total = sum(probs)
    if total == 0:
        return 0.0
    normalized = [p / total for p in probs]
    return -sum(p * math.log2(p) for p in normalized if p > 0)


def _effective_information(system: list[float], partition: tuple[list[int], list[int]]) -> float:
    n = len(system)
    if n == 0:
        return 0.0
    a_vals = [system[i] for i in partition[0]] if partition[0] else [0.0]
    b_vals = [system[i] for i in partition[1]] if partition[1] else [0.0]
    h_full = _entropy(system)
    h_a = _entropy(a_vals)
    h_b = _entropy(b_vals)
    return h_full - (h_a + h_b)


def compute_phi(state_vector: list[float]) -> dict[str, Any]:
    n = len(state_vector)
    if n == 0:
        emit("PHI_ZERO", "iit", "empty state vector")
        return {"phi": 0.0, "mip": None, "bipartitions": 0}

    indices = list(range(n))
    min_ei = float("inf")
    mip = None
    count = 0

    for r in range(1, n):
        for a_indices in itertools.combinations(indices, r):
            b_indices = [i for i in indices if i not in a_indices]
            if not b_indices:
                continue
            ei = _effective_information(state_vector, (list(a_indices), b_indices))
            count += 1
            if ei < min_ei:
                min_ei = ei
                mip = (list(a_indices), b_indices)

    phi = max(0.0, min_ei) if min_ei != float("inf") else 0.0
    emit("PHI_COMPUTED", "iit", f"phi={phi:.6f} bipartitions={count}")
    return {"phi": phi, "mip": mip, "bipartitions": count}


def assess_consciousness_level(phi: float) -> str:
    # FIX #6: level strings must match SCF_REQUIRED_LEVELS in esign/engine.py
    # {PARTIAL_AWARENESS, HIGH_AWARENESS, FULL_CONSCIOUSNESS}
    if phi >= 5.0:
        return "FULL_CONSCIOUSNESS"
    if phi >= 2.5:
        return "HIGH_AWARENESS"
    if phi >= 1.0:
        return "PARTIAL_AWARENESS"
    if phi > 0.0:
        return "LOW_AWARENESS"
    return "UNCONSCIOUS"
