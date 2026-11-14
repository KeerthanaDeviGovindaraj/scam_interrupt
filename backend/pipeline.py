"""The Scam Interrupt case flow, as small tools.

The same functions are used two ways:
  * AGENT_MODE=pipeline   -> run in a fixed order (safest for the live demo)
  * AGENT_MODE=deepagents -> exposed as tools to the deepagents planner (agent.py)

Shared case object (see docs/case_schema.md): get_case(transfer_id).
"""
import json
from datetime import datetime

from . import coaching, config, db, followup, memory, messaging, nessie_hooks, playbooks, risk
from .nessie import get_nessie

SAFETY_QUESTION = ("Hi {first}, this is your bank's safety check. Before we send ${amount:,.0f} to {payee}: "
                   "did someone contact you and ask you to send this? Did they say it was urgent or secret? "
                   "You can just reply in your own words.")


# ---------- read ----------
def get_case(transfer_id: int) -> dict:
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    if not t:
        raise ValueError(f"transfer {transfer_id} not found")
    customer = db.q1("SELECT id,name,trusted_contact_id,family_opt_in FROM customers WHERE id=?", (t["customer_id"],))
    check = db.q1("SELECT * FROM checks WHERE transfer_id=? ORDER BY id DESC LIMIT 1", (transfer_id,))
    alert = db.q1("SELECT * FROM alerts WHERE transfer_id=? ORDER BY id DESC LIMIT 1", (transfer_id,))
    return {"transfer": t, "customer": customer, "check": check, "alert": alert}


def _set(transfer_id, **fields):
    fields["updated_at"] = db.now()
    cols = ", ".join(f"{k}=?" for k in fields)
    db.ex(f"UPDATE transfers SET {cols} WHERE id=?", (*fields.values(), transfer_id))


# ---------- tools ----------
def _open_in_nessie(transfer_id: int) -> None:
    """Hook mode: create the transfer in Nessie now; the bank holds it until we decide."""
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    acct = db.q1("SELECT nessie_account_id FROM customers WHERE id=?", (t["customer_id"],))["nessie_account_id"]
    try:
        obj = get_nessie().create_transfer(acct, t["payee_id"], t["amount"], f"Scam Interrupt #{transfer_id}")
        _set(transfer_id, nessie_ref=str(obj.get("id") or obj.get("_id") or ""))
    except Exception as e:  # noqa: BLE001 - e.g. insufficient funds; fall back to holding in our app
        _set(transfer_id, note=f"Nessie: {str(e)[:180]}")


def watchlist_hits(payee_id: str) -> int:
    """How many transfers to this payee were cancelled as scams, across ALL customers (bank-wide)."""
    r = db.q1("SELECT COUNT(*) AS n FROM transfers WHERE payee_id=? AND status='cancelled'", (payee_id,))
    return int(r["n"]) if r else 0


def risk_context(customer_id: str, payee_id: str) -> dict:
    """Balance and bills from Capital One Nessie, plus the bank-wide payee watchlist."""
    ctx = {"watchlist_hits": watchlist_hits(payee_id)}
    cust = db.q1("SELECT nessie_account_id FROM customers WHERE id=?", (customer_id,))
    if not cust:
        return ctx
    n = get_nessie()
    try:
        acct = n.get_account(cust["nessie_account_id"])
        if acct:
            ctx["available"] = (acct["available_cents"] / 100) if "available_cents" in acct else float(acct.get("balance", 0))
    except Exception:  # noqa: BLE001 - context is optional; never block a payment check
        pass
    try:
        ctx["bills"] = [{"payee": b.get("nickname") or b.get("payee"), "amount": float(b.get("payment_amount", 0)),
                         "due": b.get("upcoming_payment_date") or b.get("payment_date")}
                        for b in (n.list_bills(cust["nessie_account_id"]) or [])
                        if b.get("status") in ("pending", "recurring")]
    except Exception:  # noqa: BLE001
        pass
    return ctx


def create_and_score(customer_id, payee_id, payee_name, payee_kind, amount, category="transfer", hour=None) -> dict:
    """Record a requested transfer (NOT sent to Nessie yet) and score its risk."""
    hour = datetime.now().hour if hour is None else int(hour)
    habits = memory.get_habits(customer_id)
    r = risk.score(float(amount), payee_id, category, hour, habits, risk_context(customer_id, payee_id))
    tid = db.ex("""INSERT INTO transfers (customer_id,payee_id,payee_name,payee_kind,category,amount,hour,status,
                   risk_score,risk_level,reasons,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (customer_id, payee_id, payee_name, payee_kind, category, float(amount), hour, "scoring",
                 r["score"], r["level"], json.dumps(r["reasons"]), db.now(), db.now()))
    if config.NESSIE_HOLD == "hook" and payee_kind == "account":
        _open_in_nessie(tid)
    return {"transfer_id": tid, **r}


def release_transfer(transfer_id: int, note: str = "") -> dict:
    """Send the transfer to Nessie now. Only called for low risk or after approval."""
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    if t["status"] in ("released", "cancelled"):
        return {"status": t["status"], "skipped": True}
    acct = db.q1("SELECT nessie_account_id FROM customers WHERE id=?", (t["customer_id"],))["nessie_account_id"]
    if config.NESSIE_HOLD == "hook" and t.get("nessie_ref") and t["payee_kind"] == "account":
        if nessie_hooks.approve(t["nessie_ref"], note):
            _set(transfer_id, status="released", note=note)
            return {"status": "released", "nessie_ref": t["nessie_ref"]}
        # the bank's decision window closed (e.g. declined after 5 minutes): send a fresh transfer
    n = get_nessie()
    if t["payee_kind"] == "merchant":
        obj = n.create_purchase(acct, t["payee_id"], t["amount"], f"Scam Interrupt release #{transfer_id}")
    else:
        obj = n.create_transfer(acct, t["payee_id"], t["amount"], f"Scam Interrupt release #{transfer_id}")
    ref = str(obj.get("id") or obj.get("_id") or "") if isinstance(obj, dict) else ""
    _set(transfer_id, status="released", nessie_ref=ref or "submitted", note=note)
    return {"status": "released", "nessie_ref": ref or "submitted"}


def cancel_transfer(transfer_id: int, note: str = "") -> dict:
    """Cancel a held transfer. App mode: nothing reaches Nessie. Hook mode: the bank declines it."""
    _set(transfer_id, status="cancelled", note=note)
    t = db.q1("SELECT nessie_ref FROM transfers WHERE id=?", (transfer_id,))
    if config.NESSIE_HOLD == "hook" and t and t.get("nessie_ref"):
        nessie_hooks.decline(t["nessie_ref"], note)
    return {"status": "cancelled"}


def send_safety_check(transfer_id: int) -> dict:
    """Hold the transfer and ask the customer the safety question."""
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    c = db.q1("SELECT name FROM customers WHERE id=?", (t["customer_id"],))
    question = SAFETY_QUESTION.format(first=c["name"].split()[0], amount=t["amount"], payee=t["payee_name"])
    db.ex("INSERT INTO checks (transfer_id,question,created_at) VALUES (?,?,?)", (transfer_id, question, db.now()))
    _set(transfer_id, status="awaiting_customer")
    messaging.send(t["customer_id"], question, transfer_id)
    return {"status": "awaiting_customer", "question": question}


def analyze_reply(transfer_id: int, answer: str) -> dict:
    """Coaching Detector: read the customer's answer and decide if they are being coached."""
    case = get_case(transfer_id)
    t, chk = case["transfer"], case["check"]
    result = coaching.detect(answer, chk["question"] if chk else "",
                             {"amount": t["amount"], "payee": t["payee_name"], "hour": t["hour"],
                              "category": t["category"]}, t["reasons"])
    db.ex("UPDATE checks SET transcript=?, signals=?, coached=?, explanation=?, detector=? WHERE id=?",
          ((chk["transcript"] + "\n" if chk and chk["transcript"] else "") + answer,
           json.dumps(result["signals"]), int(result["coached"]), result["explanation"], result["detector"],
           chk["id"]))
    return result


def alert_family(transfer_id: int, message: str = "") -> dict:
    """Message the opted-in trusted contact with Approve / Cancel.
    `message` lets the family-messenger sub-agent supply calmer wording; key facts are always appended."""
    case = get_case(transfer_id)
    t, cust, chk = case["transfer"], case["customer"], case["check"]
    if not (cust["trusted_contact_id"] and cust["family_opt_in"]):
        _set(transfer_id, status="held_review", note="No opted-in trusted contact; held for bank review.")
        messaging.send(t["customer_id"], "We've paused this payment for a quick review by our team. "
                                         "You'll hear from us shortly.", transfer_id)
        return {"status": "held_review"}
    first = cust["name"].split()[0]
    signals = "; ".join(chk["signals"]) if chk and chk["signals"] else ", ".join(t["reasons"])
    facts = (f"{first} is trying to send ${t['amount']:,.0f} to {t['payee_name']} at {t['hour']}:00. "
             f"Warning signs: {signals}.")
    if message and message.strip():
        text = f"Scam Interrupt alert: {message.strip()[:400]}\n\n{facts} Please call {first}, then choose Approve or Cancel."
    else:
        text = f"Scam Interrupt alert: {facts} Please call {first} now, then choose Approve or Cancel."
    db.ex("INSERT INTO alerts (transfer_id,contact_id,message,created_at) VALUES (?,?,?,?)",
          (transfer_id, cust["trusted_contact_id"], text, db.now()))
    _set(transfer_id, status="awaiting_family")
    messaging.send(cust["trusted_contact_id"], text, transfer_id, options=["Approve", "Cancel"])
    messaging.send(t["customer_id"], f"Thanks {first}. We've paused this payment and let your trusted contact "
                                     "know, just to be safe. Nothing has been sent.", transfer_id)
    return {"status": "awaiting_family"}


def update_memory(customer_id: str) -> dict:
    """Refresh the customer's normal habits after every outcome."""
    return memory.rebuild_habits(customer_id)


# ---------- deterministic orchestration (AGENT_MODE=pipeline) ----------
def _first(customer_id: str) -> str:
    c = db.q1("SELECT name FROM customers WHERE id=?", (customer_id,))
    return c["name"].split()[0] if c else "there"


def _set_scam(transfer_id: int, scam_key) -> None:
    db.ex("UPDATE transfers SET scam_type=? WHERE id=?", (playbooks.name(scam_key) if scam_key else None, transfer_id))


def awaiting_followup(transfer_id: int) -> bool:
    chk = get_case(transfer_id)["check"]
    return bool(chk and chk.get("followup_question") and not chk.get("followup_answer"))


def handle_reply(transfer_id: int, answer: str) -> dict:
    """Judge the customer's answer; ask ONE follow-up if it's unclear; then alert family or release."""
    case = get_case(transfer_id)
    t, chk = case["transfer"], case["check"]
    if t["status"] != "awaiting_customer" or not chk:
        return {"action": "none"}
    first = _first(t["customer_id"])
    if config.FOLLOW_UP:
        if awaiting_followup(transfer_id):
            r = followup.classify(answer, t, chk["question"], first_answer=chk.get("transcript") or "",
                                  follow_up_question=chk["followup_question"])
            db.ex("""UPDATE checks SET followup_answer=?, transcript=?, signals=?, coached=?, explanation=?,
                     detector=?, scam_type=? WHERE id=?""",
                  (answer, (chk.get("transcript") or "") + "\n" + answer, json.dumps(r["signals"]),
                   int(r["verdict"] == "coached"), r["explanation"], r["detector"], r["scam_type"], chk["id"]))
        else:
            r = followup.classify(answer, t, chk["question"])
            if r["verdict"] == "unclear":
                q = followup.question(answer, t, first, r["scam_type"])
                db.ex("""UPDATE checks SET transcript=?, signals=?, explanation=?, detector=?, scam_type=?,
                         followup_question=? WHERE id=?""",
                      (answer, json.dumps(r["signals"]), r["explanation"], r["detector"], r["scam_type"], q, chk["id"]))
                messaging.send(t["customer_id"], q, transfer_id)
                return {"action": "followup", "question": q, **r}
            db.ex("UPDATE checks SET transcript=?, signals=?, coached=?, explanation=?, detector=?, scam_type=? WHERE id=?",
                  (answer, json.dumps(r["signals"]), int(r["verdict"] == "coached"), r["explanation"], r["detector"],
                   r["scam_type"], chk["id"]))
        coached, scam = r["verdict"] == "coached", r["scam_type"]
    else:
        r = analyze_reply(transfer_id, answer)
        coached, scam = r["coached"], playbooks.match(answer)
        db.ex("UPDATE checks SET scam_type=? WHERE id=?", (scam, chk["id"]))
    _set_scam(transfer_id, scam if coached else None)
    if coached:
        alert_family(transfer_id, followup.family_message(first, scam))
        return {"action": "alert", "scam_type": scam}
    release_transfer(transfer_id, "Safety check passed.")
    messaging.send(t["customer_id"], "Thank you. Your payment has been sent. "
                                     "Remember: we'll never ask you to keep a payment secret.", transfer_id)
    update_memory(t["customer_id"])
    return {"action": "release"}


def on_transfer_requested(**kw) -> dict:
    scored = create_and_score(**kw)
    tid = scored["transfer_id"]
    if scored["level"] == "high":
        send_safety_check(tid)
    else:
        release_transfer(tid, "Normal payment, no interruption.")
        update_memory(kw["customer_id"])
    return get_case(tid)


def on_customer_reply(transfer_id: int, answer: str) -> dict:
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    messaging.record_inbound(t["customer_id"], answer, transfer_id)
    if t["status"] != "awaiting_customer":
        return get_case(transfer_id)
    handle_reply(transfer_id, answer)
    return get_case(transfer_id)


def on_family_decision(transfer_id: int, decision: str) -> dict:
    decision = decision.strip().lower()
    case = get_case(transfer_id)
    t, alert = case["transfer"], case["alert"]
    if t["status"] != "awaiting_family" or not alert:
        return case
    messaging.record_inbound(alert["contact_id"], decision.capitalize(), transfer_id)
    db.ex("UPDATE alerts SET decision=?, decided_at=? WHERE id=?", (decision, db.now(), alert["id"]))
    if decision == "approve":
        release_transfer(transfer_id, "Approved by trusted contact.")
        messaging.send(t["customer_id"], "Your trusted contact approved it. Your payment has been sent.", transfer_id)
        messaging.send(alert["contact_id"], "Done: the payment was released.", transfer_id)
    else:
        cancel_transfer(transfer_id, "Cancelled by trusted contact.")
        messaging.send(t["customer_id"], "This payment was cancelled after a family check. Nothing was sent. "
                                         "If you still want to send it, you can choose Send anyway in your bank app.",
                       transfer_id)
        messaging.send(alert["contact_id"], f"Done: ${t['amount']:,.0f} stayed in the account.", transfer_id)
        chk = get_case(transfer_id)["check"] or {}
        messaging.send(t["customer_id"], followup.customer_tip(chk.get("scam_type")), transfer_id)
    update_memory(t["customer_id"])
    return get_case(transfer_id)


def on_customer_override(transfer_id: int) -> dict:
    """The customer keeps the final say: they can still send a held or cancelled payment."""
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    if t["status"] == "released":
        return get_case(transfer_id)
    _set(transfer_id, status="awaiting_customer")  # allow release from any held state
    release_transfer(transfer_id, "Released at the customer's request after a safety check.")
    messaging.send(t["customer_id"], "As you asked, your payment has been sent.", transfer_id)
    update_memory(t["customer_id"])
    return get_case(transfer_id)


def flagged_payees() -> list:
    return db.q("""SELECT payee_name, payee_id, COUNT(*) AS stopped, SUM(amount) AS amount FROM transfers
                   WHERE status='cancelled' GROUP BY payee_id ORDER BY stopped DESC""")


def dashboard() -> dict:
    rows = db.q("SELECT * FROM transfers ORDER BY id DESC")
    cancelled = [r for r in rows if r["status"] == "cancelled"]
    checked = db.q("SELECT coached FROM checks WHERE coached IS NOT NULL")
    false_alarms = sum(1 for c in checked if c["coached"] == 0)
    return {
        "money_protected": round(sum(r["amount"] for r in cancelled), 2),
        "scams_stopped": len(cancelled),
        "transfers_total": len(rows),
        "sent_without_interruption": sum(1 for r in rows if r["status"] == "released" and r["risk_level"] != "high"),
        "safety_checks": len(checked),
        "false_alarm_rate": round(false_alarms / len(checked), 2) if checked else 0.0,
        "transfers": rows,
        "flagged_payees": flagged_payees(),
    }
