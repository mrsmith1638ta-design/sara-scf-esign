"""
sara-scf-esign — SCF-Gated Electronic Signature Service.

Merge of:
  sara-consciousness-hybrid  (SCF cognitive pipeline — IIT/GWT/LIDA/NCC/hybrid/safety)
  sara-pharma-esign          (21 CFR Part 11 two-component Ed25519 e-signature)

Signature issuance flow:
  1. HMAC-SHA3-512 inter-service envelope verified                (crypto layer)
  2. Two-component TOTP auth verified                             (21 CFR §11.200)
     a. password_hash  — HMAC-SHA3-512 of actor credential
     b. totp_token     — SHA3-512 HOTP 6-char window code
  3. SCF cognitive pipeline evaluated against signing stimulus    (SCF gate)
     a. IIT phi computed from stimulus hash state vector
     b. NCC signals derived from actor+record identity
     c. LIDA full cognitive cycle run on stimulus
     d. GWT competition between LIDA and NCC candidates
     e. Hybrid synthesis produces composite + consciousness_level
     f. Safety gate checks composite and NCC ceilings
     g. consciousness_level must be in {PARTIAL_AWARENESS, HIGH_AWARENESS,
        FULL_CONSCIOUSNESS} AND safety decision must be ALLOW
  4. Ed25519 signature issued over canonical manifest             (crypto layer)
  5. Audit chain entry appended                                   (ledger)

Hard-blocks at any step: no degraded path, no silent fallback.
"""

import hashlib
import hmac
import os
import time

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Optional

from scf.common.crypto import verify_envelope, build_envelope
from scf.common.audit import emit as scf_emit, tail as scf_tail, verify_chain as scf_verify_chain
from scf.iit.engine import compute_phi, assess_consciousness_level
from scf.gwt.workspace import broadcast, read_workspace, get_broadcast_log
from scf.lida.cycle import run_full_cycle
from scf.ncc.correlates import compute_ncc_index, integrate_with_iit
from scf.hybrid.synthesizer import synthesize
from scf.safety.gate import run_safety_gate
from auth.totp import verify_two_components, revoke_actor, get_failure_log, is_revoked
from esign.engine import (
    issue_signature, verify_signature,
    get_scf_rejections, get_issued_count, public_key_hex,
)
from audit.ledger import emit as ledger_emit, tail as ledger_tail, verify_chain as ledger_verify

ONTOLOGICAL_ANCHOR = "0aa4755159bf24d69acd4e8608445bbe"
MODULE_ID = "sara-scf-esign"
VERSION = "1.0.0"
TIMESTAMP_SKEW = 120
CFR_PART_11 = "21 CFR Part 11 Subpart C"
ICH_E6 = "ICH E6(R2)"

# FIX #8: gate API docs by env var — disabled in production, enabled in dev/Cursor
_ENV = os.environ.get("SARA_ENV", "production")
app = FastAPI(
    title="sara-scf-esign",
    version=VERSION,
    docs_url="/docs" if _ENV != "production" else None,
    redoc_url="/redoc" if _ENV != "production" else None,
    openapi_url="/openapi.json" if _ENV != "production" else None,
)


# ── Envelope auth ──────────────────────────────────────────────────────────────

def _hmac_secret() -> bytes:
    return os.environ["SCF_ESIGN_HMAC_SECRET"].encode()


def _auth(request: Request, body: bytes):
    m = request.headers.get("X-SARA-Module", "")
    ts = request.headers.get("X-SARA-Timestamp", "")
    sig = request.headers.get("X-SARA-Signature", "")
    if not verify_envelope(m, ts, sig, body):
        raise HTTPException(403, "FORBIDDEN")


# ── Request models ─────────────────────────────────────────────────────────────

class SignRequest(BaseModel):
    actor: str
    printed_name: str
    password_hash: str
    totp_token: str
    meaning: str
    record_id: str
    record_content_hash: str


class VerifyRequest(BaseModel):
    signature_id: str
    record_content_hash: str


class RevokeRequest(BaseModel):
    actor: str
    reason: str


class SCFPhiRequest(BaseModel):
    state_vector: list[float]


class SCFNccRequest(BaseModel):
    signals: dict[str, float]


class SCFLidaRequest(BaseModel):
    stimulus: dict[str, Any]


class SCFSynthesisRequest(BaseModel):
    state_vector: list[float]
    ncc_signals: dict[str, float]
    stimulus: dict[str, Any]
    gwt_candidates: list[dict[str, Any]] = []


class DevAttestRequest(BaseModel):
    actor: str
    printed_name: str
    record_id: str
    record_content_hash: str
    meaning: str = "authorship"


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    ledger_emit("HEALTH_CHECK", MODULE_ID)
    return {
        "status": "SOVEREIGN_OPERATIONAL",
        "module": MODULE_ID,
        "version": VERSION,
        "anchor": ONTOLOGICAL_ANCHOR,
        "regulation": [CFR_PART_11, ICH_E6],
        "public_key_hex": public_key_hex(),
        "signatures_issued": get_issued_count(),
        "ts": int(time.time()),
    }


# ── E-Signature endpoints ──────────────────────────────────────────────────────

@app.post("/v1/sign")
async def sign(req: SignRequest, request: Request):
    body = await request.body()
    _auth(request, body)

    if is_revoked(req.actor):
        ledger_emit("SIGN_REJECTED_REVOKED", MODULE_ID, f"actor={req.actor}")
        raise HTTPException(403, "ACTOR_REVOKED")

    # Step 1: Two-component TOTP authentication
    auth_result = verify_two_components(req.actor, req.password_hash, req.totp_token)
    if not auth_result["authorized"]:
        ledger_emit("SIGN_AUTH_FAIL", MODULE_ID,
                    f"actor={req.actor} reason={auth_result['reason']}")
        raise HTTPException(401, auth_result["reason"])

    # Step 2: SCF cognitive gate + Ed25519 signature issuance
    try:
        manifest = issue_signature(
            actor=req.actor,
            printed_name=req.printed_name,
            meaning=req.meaning,
            record_id=req.record_id,
            record_content_hash=req.record_content_hash,
        )
    except ValueError as e:
        ledger_emit("SIGN_SCF_BLOCKED", MODULE_ID,
                    f"actor={req.actor} error={str(e)[:120]}")
        raise HTTPException(422, str(e))

    ledger_emit("SIGN_ISSUED", MODULE_ID,
                f"actor={req.actor} sig={manifest['signature_id']} "
                f"level={manifest['scf_consciousness_level']} "
                f"composite={manifest['scf_composite']}")

    return {
        "signature_id": manifest["signature_id"],
        "manifest_hash": manifest["manifest_hash"],
        "ed25519_signature": manifest["ed25519_signature"],
        "scf_consciousness_level": manifest["scf_consciousness_level"],
        "scf_composite": manifest["scf_composite"],
        "regulation": manifest["regulation"],
        "ts": manifest["ts"],
        "module": MODULE_ID,
    }


@app.post("/v1/verify")
async def verify(req: VerifyRequest, request: Request):
    body = await request.body()
    _auth(request, body)
    result = verify_signature(req.signature_id, req.record_content_hash)
    ledger_emit("SIGN_VERIFY", MODULE_ID,
                f"sig={req.signature_id} valid={result['valid']}")
    if not result["valid"]:
        raise HTTPException(422, result.get("reason", "INVALID"))
    return result


@app.post("/v1/revoke")
async def revoke(req: RevokeRequest, request: Request):
    body = await request.body()
    _auth(request, body)
    revoke_actor(req.actor)
    ledger_emit("ACTOR_REVOKED", MODULE_ID,
                f"actor={req.actor} reason={req.reason}")
    return {"revoked": req.actor, "ts": int(time.time())}


@app.post("/v1/dev/sign-attestation")
async def dev_sign_attestation(req: DevAttestRequest, request: Request):
    """
    Dev endpoint — bypasses TOTP auth, SCF gate still runs.
    For use in test/dev environments only.
    """
    body = await request.body()
    _auth(request, body)

    if is_revoked(req.actor):
        raise HTTPException(403, "ACTOR_REVOKED")

    try:
        manifest = issue_signature(
            actor=req.actor,
            printed_name=req.printed_name,
            meaning=req.meaning,
            record_id=req.record_id,
            record_content_hash=req.record_content_hash,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    ledger_emit("DEV_ATTESTATION_ISSUED", MODULE_ID,
                f"actor={req.actor} sig={manifest['signature_id']}")
    return {
        "signature_id": manifest["signature_id"],
        "manifest": manifest,
        "note": "DEV_ENDPOINT_SCF_GATE_ACTIVE",
        "ts": manifest["ts"],
    }


@app.get("/v1/scf-rejections")
def scf_rejections(n: int = 20):
    return {"rejections": get_scf_rejections(n), "ts": int(time.time())}


# ── SCF direct-access endpoints ────────────────────────────────────────────────

@app.post("/scf/phi")
async def scf_phi(req: SCFPhiRequest, request: Request):
    body = await request.body()
    _auth(request, body)
    result = compute_phi(req.state_vector)
    result["level"] = assess_consciousness_level(result["phi"])
    scf_emit("API_PHI", MODULE_ID)
    return result


@app.post("/scf/ncc")
async def scf_ncc(req: SCFNccRequest, request: Request):
    body = await request.body()
    _auth(request, body)
    result = compute_ncc_index(req.signals)
    scf_emit("API_NCC", MODULE_ID)
    return result


@app.post("/scf/lida")
async def scf_lida(req: SCFLidaRequest, request: Request):
    body = await request.body()
    _auth(request, body)
    result = run_full_cycle(req.stimulus)
    scf_emit("API_LIDA", MODULE_ID)
    return result


@app.post("/scf/synthesize")
async def scf_synthesize(req: SCFSynthesisRequest, request: Request):
    body = await request.body()
    _auth(request, body)

    from scf.gwt.workspace import competition as gwt_competition
    iit_result = compute_phi(req.state_vector)
    ncc_result = compute_ncc_index(req.ncc_signals)
    lida_result = run_full_cycle(req.stimulus)
    gwt_result = gwt_competition(req.gwt_candidates) if req.gwt_candidates else {"salience": 0.0}
    synthesis = synthesize(iit_result, gwt_result, lida_result, ncc_result)
    safety = run_safety_gate(synthesis, ncc_result)
    integration = integrate_with_iit(iit_result["phi"], ncc_result["ncc_index"])

    scf_emit("API_SYNTHESIZE", MODULE_ID,
             f"level={synthesis['consciousness_level']} safety={safety['decision']}")
    return {
        "iit": iit_result,
        "gwt": gwt_result,
        "lida": lida_result,
        "ncc": ncc_result,
        "synthesis": synthesis,
        "safety": safety,
        "iit_ncc_integration": integration,
    }


@app.get("/scf/workspace")
def scf_workspace():
    return read_workspace()


@app.get("/scf/broadcast-log")
def scf_broadcast_log():
    return get_broadcast_log(20)


# ── Audit endpoints ────────────────────────────────────────────────────────────

@app.get("/audit/tail")
def audit_tail_ep(n: int = 20):
    return {
        "ledger": ledger_tail(n),
        "ledger_chain": ledger_verify(),
        "scf_chain": {"valid": scf_verify_chain()},
        "ts": int(time.time()),
    }


@app.get("/audit/auth-failures")
def auth_failures(n: int = 20):
    return {"failures": get_failure_log(n), "ts": int(time.time())}
