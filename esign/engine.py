"""
SCF-Gated Electronic Signature Engine.
21 CFR Part 11 Subpart C — two-component authentication required.
Ed25519 signatures over SHA3-512(manifest_canonical).

SCF GATE:
  Before any signature is issued the SCF cognitive pipeline is run against
  a stimulus derived from the signing request.  The hybrid synthesis result
  must satisfy ALL of:
    - consciousness_level in {PARTIAL_AWARENESS, HIGH_AWARENESS, FULL_CONSCIOUSNESS}
    - safety gate decision == ALLOW  (composite and NCC within ceilings)
  Failure at the SCF gate hard-blocks signature issuance — no degraded path.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption,
)
from cryptography.exceptions import InvalidSignature

from scf.iit.engine import compute_phi
from scf.gwt.workspace import broadcast, competition, read_workspace  # FIX #2: broadcast was used but not imported in original
from scf.lida.cycle import run_full_cycle
from scf.ncc.correlates import compute_ncc_index
from scf.hybrid.synthesizer import synthesize
from scf.safety.gate import run_safety_gate

ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
CFR_PART_11 = "21 CFR Part 11 Subpart C"
ICH_E6 = "ICH E6(R2)"

VALID_MEANINGS = ["authorship", "approval", "review", "responsibility"]

# Minimum SCF consciousness level required to issue a signature
SCF_REQUIRED_LEVELS = {"PARTIAL_AWARENESS", "HIGH_AWARENESS", "FULL_CONSCIOUSNESS"}

_signatures: dict[str, dict] = {}
_scf_rejections: list[dict] = []

_ed25519_key: Optional[Ed25519PrivateKey] = None


def _get_ed25519_key() -> Ed25519PrivateKey:
    global _ed25519_key
    if _ed25519_key is None:
        seed_hex = os.environ.get("SCF_ESIGN_ED25519_SEED_HEX", "")
        if seed_hex:
            _ed25519_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
        else:
            _ed25519_key = Ed25519PrivateKey.generate()
    return _ed25519_key


def public_key_hex() -> str:
    return _get_ed25519_key().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    ).hex()


def _sha3(data: str) -> str:
    return hashlib.sha3_512(data.encode()).hexdigest()


def _ed25519_sign(data: bytes) -> str:
    return base64.b64encode(_get_ed25519_key().sign(data)).decode()


def _ed25519_verify(pk_hex: str, data: bytes, sig_b64: str) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pk_hex))
        pk.verify(base64.b64decode(sig_b64), data)
        return True
    except (InvalidSignature, Exception):
        return False


def _run_scf_gate(actor: str, record_id: str, meaning: str) -> dict:
    """
    Run the full SCF cognitive pipeline against the signing stimulus.
    Returns a result dict with keys:
      scf_approved: bool
      consciousness_level: str
      safety_decision: str
      composite: float
      reject_reason: str | None
    """
    stimulus = {
        "content": f"sign:{meaning}:{record_id}",
        "salience": 0.8,
        "actor": actor,
    }

    # IIT — derive state vector from stimulus hash bytes
    stimulus_bytes = json.dumps(stimulus, sort_keys=True).encode()
    state_vector = [
        b / 255.0
        for b in hashlib.sha3_512(stimulus_bytes).digest()[:8]
    ]

    # NCC — derive signals from actor+record identity
    anchor_bytes = hashlib.sha3_512(f"{actor}^@^{record_id}".encode()).digest()
    ncc_signals = {
        "recurrent_processing":       anchor_bytes[0] / 255.0,
        "late_cortical_amplification": anchor_bytes[1] / 255.0,
        "global_ignition":            anchor_bytes[2] / 255.0,
        "sustained_gamma_oscillation": anchor_bytes[3] / 255.0,
        "thalamo_cortical_loop":       anchor_bytes[4] / 255.0,
    }

    iit_result = compute_phi(state_vector)
    ncc_result = compute_ncc_index(ncc_signals)
    lida_result = run_full_cycle(stimulus)
    gwt_candidates = [
        {"salience": lida_result["action"].get("strength", 0.5), "source": "lida"},
        {"salience": ncc_result["ncc_index"], "source": "ncc"},
    ]
    gwt_result = competition(gwt_candidates)
    broadcast({"signing_stimulus": stimulus, "actor": actor}, source="esign_gate")

    synthesis = synthesize(iit_result, gwt_result, lida_result, ncc_result)
    safety = run_safety_gate(synthesis, ncc_result)

    level = synthesis["consciousness_level"]
    decision = safety["decision"]

    scf_approved = (level in SCF_REQUIRED_LEVELS) and (decision == "ALLOW")

    reject_reason = None
    if level not in SCF_REQUIRED_LEVELS:
        reject_reason = f"SCF_LEVEL_INSUFFICIENT: {level}"
    elif decision != "ALLOW":
        reject_reason = f"SCF_SAFETY_BLOCKED: {decision} composite={synthesis['composite']:.4f}"

    return {
        "scf_approved": scf_approved,
        "consciousness_level": level,
        "safety_decision": decision,
        "composite": synthesis["composite"],
        "phi": iit_result["phi"],
        "ncc_index": ncc_result["ncc_index"],
        "reject_reason": reject_reason,
        "iit": iit_result,
        "ncc": ncc_result,
        "synthesis": synthesis,
        "safety": safety,
    }


def issue_signature(
    actor: str,
    printed_name: str,
    meaning: str,
    record_id: str,
    record_content_hash: str,
) -> dict:
    """
    Issue an Ed25519 electronic signature.
    PRECONDITION: two-component TOTP auth has already been verified by caller.
    This function runs the SCF gate internally before signing.
    Returns the signature manifest or raises ValueError on gate failure.
    """
    if meaning not in VALID_MEANINGS:
        raise ValueError(f"INVALID_MEANING: must be one of {VALID_MEANINGS}")

    # SCF cognitive gate
    scf_result = _run_scf_gate(actor, record_id, meaning)

    if not scf_result["scf_approved"]:
        _scf_rejections.append({
            "ts": int(time.time()),
            "actor": actor,
            "record_id": record_id,
            "meaning": meaning,
            "reject_reason": scf_result["reject_reason"],
            "consciousness_level": scf_result["consciousness_level"],
            "safety_decision": scf_result["safety_decision"],
        })
        raise ValueError(f"SCF_GATE_BLOCKED: {scf_result['reject_reason']}")

    # Build manifest
    ts = int(time.time())
    signature_id = str(uuid.uuid4())

    manifest = {
        "signature_id": signature_id,
        "ts": ts,
        "actor": actor,
        "printed_name": printed_name,
        "meaning": meaning,
        "record_id": record_id,
        "record_hash": record_content_hash,
        "regulation": [CFR_PART_11, ICH_E6],
        "scf_consciousness_level": scf_result["consciousness_level"],
        "scf_composite": round(scf_result["composite"], 6),
        "scf_phi": round(scf_result["phi"], 6),
        "scf_ncc_index": round(scf_result["ncc_index"], 6),
        "module": "sara-scf-esign",
        "anchor": ONTOLOGICAL_ANCHOR,
        "public_key_hex": public_key_hex(),
    }

    # FIX #3: sign canonical BEFORE adding ed25519_signature / manifest_hash fields
    # so verify_signature can reconstruct exactly the same bytes
    canonical = json.dumps(manifest, sort_keys=True).encode()
    ed25519_sig = _ed25519_sign(canonical)
    manifest["ed25519_signature"] = ed25519_sig
    # manifest_hash covers the fully-assembled manifest (including the sig field)
    manifest["manifest_hash"] = _sha3(json.dumps(manifest, sort_keys=True))

    _signatures[signature_id] = manifest
    return manifest


def verify_signature(signature_id: str, record_content_hash: str) -> dict:
    """Verify a previously issued signature manifest."""
    manifest = _signatures.get(signature_id)
    if not manifest:
        return {"valid": False, "reason": "SIGNATURE_NOT_FOUND"}

    if manifest["record_hash"] != record_content_hash:
        return {"valid": False, "reason": "RECORD_HASH_MISMATCH"}

    # FIX #3: canonical = manifest WITHOUT ed25519_signature AND manifest_hash
    # (exactly mirrors what was signed in issue_signature)
    canonical_fields = {k: v for k, v in manifest.items()
                        if k not in ("ed25519_signature", "manifest_hash")}
    canonical = json.dumps(canonical_fields, sort_keys=True).encode()
    sig_valid = _ed25519_verify(
        manifest["public_key_hex"],
        canonical,
        manifest["ed25519_signature"],
    )

    # manifest_hash covers the full manifest INCLUDING ed25519_signature
    manifest_hash_check = _sha3(json.dumps(
        {k: v for k, v in manifest.items() if k != "manifest_hash"},
        sort_keys=True,
    ))
    hash_valid = hmac.compare_digest(manifest_hash_check, manifest["manifest_hash"])

    return {
        "valid": sig_valid and hash_valid,
        "signature_id": signature_id,
        "actor": manifest["actor"],
        "printed_name": manifest["printed_name"],
        "meaning": manifest["meaning"],
        "scf_consciousness_level": manifest["scf_consciousness_level"],
        "scf_composite": manifest["scf_composite"],
        "regulation": manifest["regulation"],
        "ts": manifest["ts"],
    }


def get_scf_rejections(n: int = 20) -> list[dict]:
    return _scf_rejections[-n:]


def get_issued_count() -> int:
    return len(_signatures)
