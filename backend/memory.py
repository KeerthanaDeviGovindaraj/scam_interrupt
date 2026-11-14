"""Memory sub-agent: learns each customer's normal habits from Nessie history
and from released transfers, so normal payments are never interrupted."""
import json
from statistics import mean

from . import db
from .nessie import get_nessie


def rebuild_habits(customer_id: str) -> dict:
    cust = db.q1("SELECT * FROM customers WHERE id=?", (customer_id,))
    if not cust:
        raise ValueError(f"unknown customer {customer_id}")
    n = get_nessie()
    acct = cust["nessie_account_id"]
    purchases = n.list_purchases(acct) or []
    transfers = n.list_transfers(acct) or []

    payees, amounts = set(), []
    for p in purchases:
        payees.add(p.get("merchant_id"))
        amounts.append(float(p.get("amount", 0)))
    for t in transfers:
        if t.get("payer_id", acct) == acct:
            payees.add(t.get("payee_id"))
            amounts.append(float(t.get("amount", 0)))
    # transfers released through Scam Interrupt also count as normal
    for t in db.q("SELECT payee_id, amount, hour FROM transfers WHERE customer_id=? AND status='released'", (customer_id,)):
        payees.add(t["payee_id"])
        amounts.append(float(t["amount"]))
    hours = sorted({t["hour"] for t in db.q("SELECT hour FROM transfers WHERE customer_id=? AND status='released'",
                                            (customer_id,))} | set(range(8, 21)))
    habits = {
        "usual_payees": sorted(x for x in payees if x),
        "avg_amount": round(mean(amounts), 2) if amounts else 0.0,
        "max_amount": round(max(amounts), 2) if amounts else 0.0,
        "active_hours": hours,
    }
    db.ex("""INSERT INTO habits (customer_id, usual_payees, avg_amount, max_amount, active_hours, updated_at)
             VALUES (?,?,?,?,?,?)
             ON CONFLICT(customer_id) DO UPDATE SET usual_payees=excluded.usual_payees,
               avg_amount=excluded.avg_amount, max_amount=excluded.max_amount,
               active_hours=excluded.active_hours, updated_at=excluded.updated_at""",
          (customer_id, json.dumps(habits["usual_payees"]), habits["avg_amount"], habits["max_amount"],
           json.dumps(habits["active_hours"]), db.now()))
    return habits


def get_habits(customer_id: str) -> dict:
    h = db.q1("SELECT * FROM habits WHERE customer_id=?", (customer_id,))
    return h or rebuild_habits(customer_id)
