"""Simulates the Nessie v2 API (Bearer key, amount_cents, /data/seed) to test live mode offline.
Run:  python -m tests.test_nessie_v2"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({"NESSIE_MODE": "live", "NESSIE_KEY": "test", "PHOTON_MODE": "sim", "MODEL": "",
                   "DB_PATH": os.path.join(_tmp, "v2.db")})

import requests  # noqa: E402

CALLS = []


class Resp:
    def __init__(self, code, data):
        self.status_code, self._data = code, data
        self.text = "x" if data is not None else ""

    def json(self):
        return self._data


ACCOUNTS = [
    {"id": "acc_mary_chk", "customer_id": "cus_1", "type": "checking", "nickname": "Everyday Checking"},
    {"id": "acc_mary_sav", "customer_id": "cus_1", "type": "savings"},
    {"id": "acc_cc", "customer_id": "cus_1", "type": "credit_card"},
    {"id": "acc_other_chk", "customer_id": "cus_2", "type": "checking"},
]


STATE = {"customers": [{"id": "cus_1", "first_name": "Ann", "last_name": "Smith"},
                       {"id": "cus_2", "first_name": "Bo", "last_name": "Smith"}],
         "extra_accounts": [], "bills": [], "available": {"acc_mary_chk": 138000}}


def fake_request(method, url, headers=None, json=None, timeout=None):
    assert headers["Authorization"] == "Bearer test"
    path = url.split("nessieisreal.com", 1)[1].split("?")[0]
    CALLS.append((method, path, json))
    if method == "POST" and path == "/data/seed":
        return Resp(201, {"ok": True})
    if method == "GET" and path == "/accounts":
        return Resp(200, {"items": ACCOUNTS + STATE["extra_accounts"]})
    if method == "GET" and path == "/customers":
        return Resp(200, {"items": STATE["customers"]})
    if method == "POST" and path == "/customers":
        c = {"id": f"cus_{len(STATE['customers']) + 1}", **json}
        STATE["customers"].append(c); return Resp(200, c)
    if method == "GET" and path.startswith("/customers/") and path.endswith("/accounts"):
        cid = path.split("/")[2]
        return Resp(200, {"items": [a for a in ACCOUNTS + STATE["extra_accounts"] if a["customer_id"] == cid]})
    if method == "POST" and path.startswith("/customers/") and path.endswith("/accounts"):
        a = {"id": f"acc_new_{len(STATE['extra_accounts'])}", "customer_id": path.split("/")[2], **json}
        STATE["extra_accounts"].append(a); return Resp(200, a)
    if method == "GET" and path.startswith("/accounts/") and path.count("/") == 2:
        aid = path.split("/")[2]
        return Resp(200, {"id": aid, "available_cents": STATE["available"].get(aid, 0), "balance_cents": 0})
    if method == "POST" and path.endswith("/deposits"):
        aid = path.split("/")[2]
        STATE["available"][aid] = STATE["available"].get(aid, 0) + json["amount_cents"]
        return Resp(200, {"id": "txn_dep", "kind": "deposit"})
    if method == "POST" and path.endswith("/settle"):
        return Resp(200, {"id": path.split("/")[2], "status": "completed"})
    if method == "GET" and path.endswith("/bills"):
        return Resp(200, {"items": STATE["bills"]})
    if method == "POST" and path.endswith("/bills"):
        b = {"id": "bill_1", "account_id": path.split("/")[2], "upcoming_payment_date": "2026-12-01", **json}
        STATE["bills"].append(b); return Resp(200, b)
    if method == "GET" and path == "/merchants":
        return Resp(200, [{"id": "m1", "name": "Corner Grocery"}, {"id": "m2", "name": "Gift Card Hub"}])
    if method == "POST" and path.endswith("/transfers"):
        assert isinstance(json["amount_cents"], int)
        return Resp(201, {"id": f"tx{len(CALLS)}", "status": "pending"})
    return Resp(404, {"error": "not found"})


requests.request = fake_request

from backend import db, pipeline  # noqa: E402
from backend.seed import seed  # noqa: E402


def test_live_v2_flow():
    out = seed(reset=True)
    assert out["mode"] == "live" and out["mary_account"] == "acc_mary_chk"
    assert out["david_account"] == "acc_other_chk"
    assert out["ray_account"].startswith("acc_new_") and out["ray_customer"] not in ("cus_1", "cus_2")  # separate customer
    assert STATE["available"]["acc_mary_chk"] == 350000                                               # topped up to $3,500
    assert STATE["bills"] and STATE["bills"][0]["payee"] == "Princeton Rentals"
    ray = db.q1("SELECT nessie_account_id FROM customers WHERE id='ray'")["nessie_account_id"]
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                          payee_kind="account", amount=3000, hour=23)
    t = case["transfer"]
    assert t["risk_level"] == "high", t
    assert any("not enough for Rent" in r for r in t["reasons"]), t["reasons"]
    pipeline.on_customer_reply(t["id"], "No one asked me. It's for school fees. Please hurry.")
    case = pipeline.on_family_decision(t["id"], "cancel")
    assert case["transfer"]["status"] == "cancelled" and not case["transfer"]["nessie_ref"]
    # normal payment to David -> real transfer call with cents
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id="acc_other_chk", payee_name="David Lee",
                                          payee_kind="account", amount=120, hour=14)
    assert case["transfer"]["status"] == "released" and case["transfer"]["nessie_ref"].startswith("tx")
    assert any(c[2] and c[2].get("amount_cents") == 12000 for c in CALLS)


if __name__ == "__main__":
    test_live_v2_flow()
    print("PASS test_live_v2_flow")
