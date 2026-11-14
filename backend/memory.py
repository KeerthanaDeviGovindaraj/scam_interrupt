"""Memory sub-agent: learns each customer's normal habits from Nessie history and from released
transfers, so normal payments are never interrupted. If Nessie history can't be listed, a baseline
saved at seed time is used."""
import json
from statistics import mean

from . import db
from .nessie import dollars, get_nessie


def _payer(obj):
    return str(obj.get("payer_id") or obj.get("from_account_id") or obj.get("account_id") or "")


def rebuild_habits(customer_id: str) -> dict:
    cust = db.q1("SELECT * FROM customers WHERE id=?", (customer_id,))
    if not cust:
        raise ValueError(f"unknown customer {customer_id}")
    acct = cust["nessie_account_id"]
    n = get_nessie()
    payees, amounts = set(), []
    try:
        for p in n.list_purchases(acct) or []:
            payees.add(str(p.get("merchant_id") or ""))
            amounts.append(dollars(p))
        for t in n.list_transfers(acct) or []:
            if _payer(t) in ("", acct):
                payees.add(str(t.get("payee_id") or ""))
                amounts.append(dollars(t))
    except Exception:  # noqa: BLE001 - history is optional
        pass

    base = db.kv_get(f"baseline:{customer_id}")
    if base and (not amounts or len(amounts) < 3):
        payees |= set(base["usual_payees"])
        amounts += [base["avg_amount"]] * 5 + [base["max_amount"]]

    for t in db.q("SELECT payee_id, amount FROM transfers WHERE customer_id=? AND status='released'", (customer_id,)):
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
