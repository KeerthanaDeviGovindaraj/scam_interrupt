"""End-to-end test of the demo flow in offline mode (mock Nessie, simulator, rules).
Run from the repo root:  python -m pytest -q   (or: python -m tests.test_core)"""
import os
import tempfile

os.environ["NESSIE_MODE"] = "mock"
os.environ["PHOTON_MODE"] = "sim"
os.environ["MODEL"] = ""
_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "t.db")
os.environ["MOCK_NESSIE_PATH"] = os.path.join(_tmp, "n.json")

from backend import coaching, db, pipeline, risk  # noqa: E402
from backend.seed import seed  # noqa: E402


def _ids():
    s = seed(reset=True)
    ray = db.q1("SELECT nessie_account_id FROM customers WHERE id='ray'")["nessie_account_id"]
    return s, ray


def test_normal_payment_goes_straight_through():
    s, _ = _ids()
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=s["david_account"], payee_name="David Lee",
                                          payee_kind="account", amount=120, hour=14)
    assert case["transfer"]["status"] == "released"
    assert case["check"] is None


def test_grandma_scam_is_stopped_by_family():
    s, ray = _ids()
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                          payee_kind="account", amount=3000, hour=23)
    t = case["transfer"]
    assert t["risk_level"] == "high" and t["status"] == "awaiting_customer", t
    assert "new payee" in t["reasons"]
    case = pipeline.on_customer_reply(t["id"], "No one asked me. It's for school fees. Please hurry.")
    assert case["check"]["coached"] == 1, case["check"]
    assert case["transfer"]["status"] == "awaiting_family"
    case = pipeline.on_family_decision(t["id"], "cancel")
    assert case["transfer"]["status"] == "cancelled"
    assert case["transfer"]["nessie_ref"] is None          # never reached the bank
    d = pipeline.dashboard()
    assert d["money_protected"] == 3000 and d["scams_stopped"] == 1


def test_calm_answer_releases_and_customer_keeps_final_say():
    s, ray = _ids()
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                          payee_kind="account", amount=3000, hour=23)
    tid = case["transfer"]["id"]
    case = pipeline.on_customer_reply(tid, "Ray is my new contractor, I met him and checked his license.")
    assert case["transfer"]["status"] == "released"
    # override path on a different cancelled transfer
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=s["merchants"]["gift_card"],
                                          payee_name="GiftCard Depot", payee_kind="merchant", amount=500,
                                          category="gift_card", hour=23)
    tid = case["transfer"]["id"]
    pipeline.on_customer_reply(tid, "Hurry, it's urgent and secret")
    pipeline.on_family_decision(tid, "cancel")
    case = pipeline.on_customer_override(tid)
    assert case["transfer"]["status"] == "released"


def test_rules_detector():
    r = coaching.rule_detect("No one asked me. It's for school fees. Please hurry.", ["new payee"])
    assert r["coached"] and len(r["signals"]) >= 3
    r = coaching.rule_detect("It's my monthly gift to my grandson.", ["new payee"])
    assert not r["coached"]


def test_risk_scorer():
    h = {"usual_payees": ["a"], "avg_amount": 200, "max_amount": 400}
    assert risk.score(3000, "x", "transfer", 23, h)["level"] == "high"
    assert risk.score(150, "a", "transfer", 14, h)["level"] == "low"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
