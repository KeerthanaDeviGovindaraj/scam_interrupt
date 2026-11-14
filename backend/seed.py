"""Seed demo data: Grandma Mary, her grandson David, a scam payee, merchants,
and 30 days of normal purchase history.

Run:  python -m backend.seed          (uses NESSIE_MODE from .env)
"""
import random
from datetime import date, timedelta

from . import config, db
from .memory import rebuild_habits
from .nessie import get_nessie, reset_client


def seed(reset: bool = True):
    if reset:
        db.reset_db()
        if config.NESSIE_MODE != "live":
            import os
            if os.path.exists(config.MOCK_NESSIE_PATH):
                os.remove(config.MOCK_NESSIE_PATH)
            reset_client()
    else:
        db.init_db()
    n = get_nessie()

    def person(local_id, first, last, role, phone, balance):
        cust = n.create_customer(first, last)
        acct = n.create_account(cust["_id"], f"{first} Checking", balance)
        db.ex("INSERT INTO customers (id,name,phone,role,nessie_customer_id,nessie_account_id) VALUES (?,?,?,?,?,?)",
              (local_id, f"{first} {last}", phone, role, cust["_id"], acct["_id"]))
        return acct["_id"]

    mary_acct = person("mary", "Mary", "Lee", "customer", config.MARY_PHONE, 8200)
    david_acct = person("david", "David", "Lee", "family", config.DAVID_PHONE, 1500)
    person("ray", "Ray", "Collins", "payee", None, 50)          # the scammer's account
    # Mary opted in: David is her trusted contact
    db.ex("UPDATE customers SET trusted_contact_id='david', family_opt_in=1 WHERE id='mary'")

    merchants = {}
    for name, cat in [("Princeton Grocer", "grocery"), ("Nassau Pharmacy", "pharmacy"),
                      ("PSE&G Utility", "utility"), ("GiftCard Depot", "gift_card"),
                      ("QuickCoin Kiosk", "crypto")]:
        m = n.create_merchant(name, cat)
        merchants[cat] = m["_id"]
        db.ex("INSERT INTO merchants (id,name,category) VALUES (?,?,?)", (m["_id"], name, cat))

    # 30 days of normal life: groceries, pharmacy, a utility bill, two gifts to David
    rng = random.Random(7)
    today = date.today()
    for d in range(30, 0, -3):
        day = (today - timedelta(days=d)).isoformat()
        n.create_purchase(mary_acct, merchants["grocery"], round(rng.uniform(40, 140), 2), "groceries", day)
        if d % 9 == 0:
            n.create_purchase(mary_acct, merchants["pharmacy"], round(rng.uniform(15, 60), 2), "prescriptions", day)
    n.create_purchase(mary_acct, merchants["utility"], 182.40, "electric bill", (today - timedelta(days=12)).isoformat())
    n.create_transfer(mary_acct, david_acct, 100, "birthday gift")
    n.create_transfer(mary_acct, david_acct, 150, "books")

    rebuild_habits("mary")
    return {"mary_account": mary_acct, "david_account": david_acct, "merchants": merchants}


if __name__ == "__main__":
    print(seed())
