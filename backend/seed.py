"""Seed demo data: Grandma Mary, her grandson David, a scam payee, merchants, history.

Run:  python -m backend.seed          (uses NESSIE_MODE from .env)

mock -> builds everything in the offline fake bank.
live -> Nessie v2: calls POST /data/seed (a ready-made demo bank), then labels its accounts for our
        story: one checking account is "Mary Lee", another customer's account is "David Lee", and a
        third account plays the scammer "Ray Collins". The labels live only in our database.
"""
import os
import random
from datetime import date, timedelta

from . import config, db
from .memory import rebuild_habits
from .nessie import dollars, get_nessie, oid, reset_client

CATEGORY_WORDS = {
    "grocery": ["grocer", "grocery", "market", "food", "supermarket"],
    "pharmacy": ["pharm", "drug", "cvs", "walgreens", "health"],
    "utility": ["utility", "electric", "power", "water", "gas", "pse&g", "internet", "phone"],
    "gift_card": ["gift"],
    "crypto": ["crypto", "coin", "bitcoin"],
}


def _category(m: dict) -> str:
    text = " ".join(str(m.get(k, "")) for k in ("name", "category", "type")).lower()
    for cat, words in CATEGORY_WORDS.items():
        if any(w in text for w in words):
            return cat
    return "other"


def _reset_local():
    db.reset_db()
    if config.NESSIE_MODE != "live" and os.path.exists(config.MOCK_NESSIE_PATH):
        os.remove(config.MOCK_NESSIE_PATH)
    reset_client()


def _add_person(local_id, name, phone, role, customer_id, account_id):
    db.ex("INSERT INTO customers (id,name,phone,role,nessie_customer_id,nessie_account_id) VALUES (?,?,?,?,?,?)",
          (local_id, name, phone, role, customer_id, account_id))


def _finish():
    db.ex("UPDATE customers SET trusted_contact_id='david', family_opt_in=1 WHERE id='mary'")
    return rebuild_habits("mary")


# ---------------- mock ----------------
def seed_mock():
    n = get_nessie()

    def person(local_id, first, last, role, phone, balance):
        cust = n.create_customer(first, last)
        acct = n.create_account(cust["_id"], f"{first} Checking", balance)
        _add_person(local_id, f"{first} {last}", phone, role, cust["_id"], acct["_id"])
        return acct["_id"]

    mary = person("mary", "Mary", "Lee", "customer", config.MARY_PHONE, 8200)
    david = person("david", "David", "Lee", "family", config.DAVID_PHONE, 1500)
    person("ray", "Ray", "Collins", "payee", None, 50)
    merchants = {}
    for name, cat in [("Princeton Grocer", "grocery"), ("Nassau Pharmacy", "pharmacy"),
                      ("PSE&G Utility", "utility"), ("GiftCard Depot", "gift_card"), ("QuickCoin Kiosk", "crypto")]:
        m = n.create_merchant(name, cat)
        merchants[cat] = m["_id"]
        db.ex("INSERT INTO merchants (id,name,category) VALUES (?,?,?)", (m["_id"], name, cat))
    rng, today = random.Random(7), date.today()
    for d in range(30, 0, -3):
        day = (today - timedelta(days=d)).isoformat()
        n.create_purchase(mary, merchants["grocery"], round(rng.uniform(40, 140), 2), "groceries", day)
        if d % 9 == 0:
            n.create_purchase(mary, merchants["pharmacy"], round(rng.uniform(15, 60), 2), "prescriptions", day)
    n.create_purchase(mary, merchants["utility"], 182.40, "electric bill", (today - timedelta(days=12)).isoformat())
    n.create_transfer(mary, david, 100, "birthday gift")
    n.create_transfer(mary, david, 150, "books")
    habits = _finish()
    return {"mode": "mock", "mary_account": mary, "david_account": david, "merchants": merchants, "habits": habits}


# ---------------- live (Nessie v2) ----------------
def _owner(a):
    return str(a.get("customer_id") or a.get("owner_id") or a.get("customer") or "")


def _is_card(a):
    return "credit" in str(a.get("type") or a.get("account_type") or a.get("nickname") or "").lower()


def seed_live():
    n = get_nessie()
    n.seed_demo_bank()
    accounts = [a for a in n.list_accounts() if not _is_card(a)]
    if len(accounts) < 3:
        raise RuntimeError(f"Need at least 3 non-credit accounts from /data/seed, got {len(accounts)}. "
                           "Run the seed again or check GET /accounts.")
    checking = [a for a in accounts if "check" in str(a.get("type") or a.get("nickname") or "").lower()]
    mary = checking[0] if checking else accounts[0]
    others = [a for a in accounts if oid(a) != oid(mary)]
    # David: prefer a different customer's account; Ray: any remaining account
    diff_owner = [a for a in others if _owner(a) and _owner(a) != _owner(mary)]
    david = diff_owner[0] if diff_owner else others[0]
    ray = next(a for a in others if oid(a) != oid(david))

    _add_person("mary", "Mary Lee", config.MARY_PHONE, "customer", _owner(mary), oid(mary))
    _add_person("david", "David Lee", config.DAVID_PHONE, "family", _owner(david), oid(david))
    _add_person("ray", "Ray Collins", None, "payee", _owner(ray), oid(ray))

    merchants = {}
    for m in n.list_merchants():
        if oid(m):
            cat = _category(m)
            db.ex("INSERT OR IGNORE INTO merchants (id,name,category) VALUES (?,?,?)",
                  (oid(m), str(m.get("name") or "Merchant"), cat))
            merchants.setdefault(cat, oid(m))

    # Normal history: two small gifts to David (real Nessie transfers, pending -> settle on their own)
    for amt in (100, 150):
        try:
            n.create_transfer(oid(mary), oid(david), amt, "gift")
        except Exception as e:  # noqa: BLE001
            print("warning: history transfer failed:", e)

    # Baseline habits, used if Nessie history listing isn't available yet
    usual = [oid(david)] + list(merchants.values())
    db.kv_set("baseline:mary", {"usual_payees": usual, "avg_amount": 95.0, "max_amount": 182.4})
    habits = _finish()
    return {"mode": "live", "mary_account": oid(mary), "david_account": oid(david), "ray_account": oid(ray),
            "merchants": merchants, "habits": habits}


def seed(reset: bool = True):
    if reset:
        _reset_local()
    else:
        db.init_db()
    return seed_live() if config.NESSIE_MODE == "live" else seed_mock()


if __name__ == "__main__":
    import json
    print(json.dumps(seed(), indent=2, default=str))
