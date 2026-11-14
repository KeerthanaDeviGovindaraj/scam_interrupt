"""Nessie v2 decision hooks: the bank asks Scam Interrupt before a transfer settles.

NESSIE_HOLD=hook  -> transfers are created in Nessie immediately (pending, money held by the bank).
                     Nessie calls POST /webhooks/nessie-decision; we approve low risk at once, answer
                     "ask again later" (202) for risky ones, and decide out of band with
                     POST /transactions/{id}/decision once the family has answered.
NESSIE_HOLD=app   -> today's design: our app holds the transfer and only posts it after approval.

Register the hook once with scripts/register_nessie_hook.py (needs a public https URL, e.g. ngrok).
The hook is registered with on_error=decline, so if we are unreachable the bank fails safe.
"""
import hashlib
import hmac
import json
import logging

from . import config, db
from .nessie import NessieError, get_nessie

log = logging.getLogger("nessie_hooks")
RETRY_SECONDS = 25        # Nessie re-asks at most 10 times within max_wait (300 s)


def verify_signature(secret: str, header: str, body: bytes) -> bool:
    """Nessie-Signature: t=<ts>,v1=<hex hmac-sha256 over "t.body">"""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
    except Exception:  # noqa: BLE001
        return False


def decide_for(tx: dict) -> tuple[int, dict]:
    """What to answer Nessie for one pending transaction. Pure logic, easy to test."""
    t = db.q1("SELECT * FROM transfers WHERE nessie_ref=?", (str(tx.get("id", "")),))
    if not t:
        return 202, {"retry_after": 2}                         # we may not have stored the id yet
    if t["status"] == "released":
        return 200, {"decision": "approve"}
    if t["status"] == "cancelled":
        return 200, {"decision": "decline", "reason": (t.get("note") or "cancelled after a safety check")[:200]}
    if t["risk_level"] != "high":
        return 200, {"decision": "approve"}
    return 202, {"retry_after": RETRY_SECONDS}                 # still checking with the customer / family


def approve(tx_id: str, note: str = "") -> bool:
    try:
        get_nessie().decide(tx_id, "approve", note or "approved after safety check")
        return True
    except NessieError as e:
        log.warning("approve %s failed: %s", tx_id, e)
        return False


def decline(tx_id: str, reason: str = "") -> bool:
    try:
        get_nessie().decide(tx_id, "decline", reason or "cancelled after safety check")
        return True
    except NessieError as e:
        log.warning("decline %s failed: %s", tx_id, e)
        return False


try:  # FastAPI route (the module stays importable for tests without FastAPI)
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter()

    @router.post("/webhooks/nessie-decision")
    async def nessie_decision(request: Request):
        body = await request.body()
        if config.NESSIE_HOOK_SECRET and not verify_signature(config.NESSIE_HOOK_SECRET,
                                                              request.headers.get("Nessie-Signature", ""), body):
            return JSONResponse({"error": "bad signature"}, status_code=401)
        payload = json.loads(body or b"{}")
        tx = payload.get("transaction") or {}
        if not tx:
            return JSONResponse({"ok": True})                  # ping or other event
        status, data = decide_for(tx)
        headers = {"Retry-After": str(data["retry_after"])} if status == 202 else None
        log.info("nessie decision for %s -> %s %s", tx.get("id"), status, data)
        return JSONResponse(data, status_code=status, headers=headers)
except ImportError:  # pragma: no cover
    router = None
