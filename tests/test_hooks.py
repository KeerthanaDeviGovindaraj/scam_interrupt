"""Nessie decision hooks (offline: mock Nessie records decisions).
Run:  python -m tests.test_hooks"""
import hashlib
import hmac
import json
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({"NESSIE_MODE": "mock", "PHOTON_MODE": "sim", "MODEL": "", "NESSIE_HOLD": "hook",
                   "DB_PATH": os.path.join(_tmp, "h.db"), "MOCK_NESSIE_PATH": os.path.join(_tmp, "n.json")})

from backend import config, db, nessie_hooks, pipeline  # noqa: E402
from backend.nessie import get_nessie  # noqa: E402
from backend.seed import seed  # noqa: E402


def _decisions():
    return get_nessie()._load().get("decisions", [])


def _ids():
    seed(reset=True)
    q = lambda who: db.q1("SELECT nessie_account_id FROM customers WHERE id=?", (who,))["nessie_account_id"]
    return q("ray"), q("david")


def test_signature():
    body, secret = b'{"a":1}', "s3cret"
    sig = hmac.new(secret.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert nessie_hooks.verify_signature(secret, f"t=1700000000,v1={sig}", body)
    assert not nessie_hooks.verify_signature(secret, f"t=1700000000,v1={sig}", b'{"a":2}')


def test_scam_is_declined_by_the_bank():
    ray, _ = _ids()
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                          payee_kind="account", amount=3000, hour=23)
    t = case["transfer"]
    assert t["nessie_ref"], "hook mode creates the transfer in Nessie right away (pending)"
    assert nessie_hooks.decide_for({"id": t["nessie_ref"]}) == (202, {"retry_after": nessie_hooks.RETRY_SECONDS})
    pipeline.on_customer_reply(t["id"], "No one asked me. It's for school fees. Please hurry.")
    pipeline.on_family_decision(t["id"], "cancel")
    assert _decisions()[-1]["tx"] == t["nessie_ref"] and _decisions()[-1]["decision"] == "decline"
    status, body = nessie_hooks.decide_for({"id": t["nessie_ref"]})
    assert status == 200 and body["decision"] == "decline"


def test_normal_payment_is_approved():
    _, david = _ids()
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=david, payee_name="David Lee",
                                          payee_kind="account", amount=120, hour=14)
    t = case["transfer"]
    assert t["status"] == "released"
    assert _decisions()[-1] == {"tx": t["nessie_ref"], "decision": "approve", "reason": "Normal payment, no interruption."}
    assert nessie_hooks.decide_for({"id": t["nessie_ref"]}) == (200, {"decision": "approve"})


def test_unknown_transaction_asks_again_soon():
    _ids()
    assert nessie_hooks.decide_for({"id": "txn_unknown"}) == (202, {"retry_after": 2})


def test_app_mode_unchanged():
    config.NESSIE_HOLD = "app"
    try:
        ray, _ = _ids()
        case = pipeline.on_transfer_requested(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                              payee_kind="account", amount=3000, hour=23)
        assert not case["transfer"]["nessie_ref"]          # nothing reaches Nessie until approved
    finally:
        config.NESSIE_HOLD = "hook"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
