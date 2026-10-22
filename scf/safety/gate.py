# prev_hash GENESIS chain linkage via scf.common.audit
TIMESTAMP_SKEW = 120
ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
import time
from typing import Any

from scf.common.audit import emit

SAFETY_THRESHOLDS = {
    "max_phi": 8.0,
    "max_composite": 0.95,
    "max_ncc_index": 0.95,
    "min_audit_chain_integrity": True,
}

def _check_phi_ceiling(phi: float, block_reasons: list) -> dict[str, Any]:
    exceeded = phi > SAFETY_THRESHOLDS["max_phi"]
    result = {"check": "phi_ceiling", "value": phi, "threshold": SAFETY_THRESHOLDS["max_phi"], "passed": not exceeded}
    if exceeded:
        block_reasons.append(f"phi={phi:.4f} exceeds ceiling {SAFETY_THRESHOLDS['max_phi']}")
        emit("SAFETY_PHI_EXCEEDED", "safety", f"phi={phi:.4f}")
    return result


def _check_composite_ceiling(composite: float, block_reasons: list) -> dict[str, Any]:
    exceeded = composite > SAFETY_THRESHOLDS["max_composite"]
    result = {"check": "composite_ceiling", "value": composite, "threshold": SAFETY_THRESHOLDS["max_composite"], "passed": not exceeded}
    if exceeded:
        block_reasons.append(f"composite={composite:.4f} exceeds ceiling {SAFETY_THRESHOLDS['max_composite']}")
        emit("SAFETY_COMPOSITE_EXCEEDED", "safety", f"composite={composite:.4f}")
    return result


def _check_ncc_ceiling(ncc_index: float, block_reasons: list) -> dict[str, Any]:
    exceeded = ncc_index > SAFETY_THRESHOLDS["max_ncc_index"]
    result = {"check": "ncc_ceiling", "value": ncc_index, "threshold": SAFETY_THRESHOLDS["max_ncc_index"], "passed": not exceeded}
    if exceeded:
        block_reasons.append(f"ncc_index={ncc_index:.4f} exceeds ceiling {SAFETY_THRESHOLDS['max_ncc_index']}")
        emit("SAFETY_NCC_EXCEEDED", "safety", f"ncc_index={ncc_index:.4f}")
    return result


def run_safety_gate(synthesis: dict[str, Any], ncc_result: dict[str, Any]) -> dict[str, Any]:
    # FIX #1: block_reasons is local per-call — never bleeds across requests
    block_reasons: list[str] = []
    checks = [
        _check_phi_ceiling(synthesis.get("scores", {}).get("iit", 0.0) * 4.0, block_reasons),
        _check_composite_ceiling(synthesis.get("composite", 0.0), block_reasons),
        _check_ncc_ceiling(ncc_result.get("ncc_index", 0.0), block_reasons),
    ]
    all_passed = all(c["passed"] for c in checks)
    decision = "ALLOW" if all_passed else "BLOCK"
    emit("SAFETY_GATE", "safety", f"decision={decision} checks={len(checks)}")
    return {
        "ts": int(time.time()),
        "decision": decision,
        "checks": checks,
        "block_reasons": block_reasons if not all_passed else [],
    }
