"""FastAPI app: mock bank, phone simulator, dashboard, and Photon webhook.

Run from the repo root:   uvicorn backend.app:app --reload --port 8000
Then open:                http://localhost:8000
"""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, messaging, pipeline
from .seed import seed

log = logging.getLogger("app")
app = FastAPI(title="Scam Interrupt")
db.init_db()


class TransferIn(BaseModel):
    customer_id: str = "mary"
    payee_id: str
    amount: float
    hour: int | None = None          # demo override, e.g. 23 for 11 PM


class ReplyIn(BaseModel):
    text: str


class DecisionIn(BaseModel):
    decision: str                    # approve | cancel


def _use_agent() -> bool:
    return config.AGENT_MODE == "deepagents" and bool(config.MODEL)


def _payee(payee_id: str) -> dict:
    acct = db.q1("SELECT id, name, nessie_account_id FROM customers WHERE nessie_account_id=?", (payee_id,))
    if acct:
        return {"name": acct["name"], "kind": "account", "category": "transfer"}
    m = db.q1("SELECT * FROM merchants WHERE id=?", (payee_id,))
    if m:
        return {"name": m["name"], "kind": "merchant", "category": m["category"]}
    raise HTTPException(404, "Unknown payee")


@app.get("/")
def home():
    return RedirectResponse("/web/index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "nessie_mode": config.NESSIE_MODE, "photon_mode": config.PHOTON_MODE,
            "agent_mode": "deepagents" if _use_agent() else "pipeline", "model": config.MODEL or "rules"}


@app.post("/api/demo/reset")
def demo_reset():
    """Wipe and re-seed demo data (Mary, David, the scam payee, merchants, history)."""
    return seed(reset=True)


@app.get("/api/payees")
def payees(customer_id: str = "mary"):
    people = db.q("SELECT name, nessie_account_id AS id, 'account' AS kind FROM customers WHERE id != ?",
                  (customer_id,))
    merchants = db.q("SELECT name, id, 'merchant' AS kind, category FROM merchants")
    return people + merchants


@app.post("/api/transfers")
def request_transfer(body: TransferIn):
    p = _payee(body.payee_id)
    kw = dict(customer_id=body.customer_id, payee_id=body.payee_id, payee_name=p["name"], payee_kind=p["kind"],
              amount=body.amount, category=p["category"], hour=body.hour)
    if _use_agent():
        from . import agent
        scored = pipeline.create_and_score(**kw)
        try:
            agent.run("transfer_scored", scored["transfer_id"])
        except Exception as e:  # agent failed: fall back to the safe fixed flow
            log.exception("agent failed, falling back: %s", e)
            t = pipeline.get_case(scored["transfer_id"])["transfer"]
            if t["status"] == "scoring":
                (pipeline.send_safety_check if scored["level"] == "high" else
                 lambda i: pipeline.release_transfer(i, "Normal payment."))(scored["transfer_id"])
        return pipeline.get_case(scored["transfer_id"])
    return pipeline.on_transfer_requested(**kw)


@app.get("/api/transfers")
def list_transfers():
    return db.q("SELECT * FROM transfers ORDER BY id DESC")


@app.get("/api/cases/{transfer_id}")
def get_case(transfer_id: int):
    return pipeline.get_case(transfer_id)


@app.post("/api/cases/{transfer_id}/reply")
def customer_reply(transfer_id: int, body: ReplyIn):
    if _use_agent():
        from . import agent
        t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
        messaging.record_inbound(t["customer_id"], body.text, transfer_id)
        try:
            agent.run("customer_replied", transfer_id, {"answer": body.text})
        except Exception as e:
            log.exception("agent failed, falling back: %s", e)
        t = db.q1("SELECT status FROM transfers WHERE id=?", (transfer_id,))
        if t["status"] == "awaiting_customer":  # agent did nothing useful -> fixed flow
            db.ex("DELETE FROM messages WHERE id=(SELECT MAX(id) FROM messages WHERE transfer_id=? AND direction='in')",
                  (transfer_id,))
            return pipeline.on_customer_reply(transfer_id, body.text)
        return pipeline.get_case(transfer_id)
    return pipeline.on_customer_reply(transfer_id, body.text)


@app.post("/api/cases/{transfer_id}/family")
def family_decision(transfer_id: int, body: DecisionIn):
    if body.decision.lower() not in ("approve", "cancel"):
        raise HTTPException(400, "decision must be approve or cancel")
    return pipeline.on_family_decision(transfer_id, body.decision)


@app.post("/api/cases/{transfer_id}/override")
def customer_override(transfer_id: int):
    """Customer keeps the final say."""
    return pipeline.on_customer_override(transfer_id)


@app.get("/api/phone/{owner_id}")
def phone(owner_id: str):
    return messaging.inbox(owner_id)


@app.get("/api/dashboard")
def dashboard():
    return pipeline.dashboard()


@app.post("/webhooks/photon")
async def photon_webhook(request: Request):
    """Inbound messages from Photon. ADAPT the two lines below to Photon's payload format."""
    payload = await request.json()
    phone_number = payload.get("from") or payload.get("sender")       # TODO: match Photon's field name
    text = (payload.get("text") or payload.get("body") or "").strip()   # TODO: match Photon's field name
    person = db.q1("SELECT * FROM customers WHERE phone=?", (phone_number,))
    if not person or not text:
        return {"ignored": True}
    waiting = db.q1("SELECT id FROM transfers WHERE customer_id=? AND status='awaiting_customer' ORDER BY id DESC",
                    (person["id"],))
    if waiting:
        return customer_reply(waiting["id"], ReplyIn(text=text))
    fam = db.q1("""SELECT t.id FROM transfers t JOIN alerts a ON a.transfer_id=t.id
                   WHERE a.contact_id=? AND t.status='awaiting_family' ORDER BY t.id DESC""", (person["id"],))
    if fam:
        word = text.lower()
        if "approve" in word or word in ("yes", "y"):
            return family_decision(fam["id"], DecisionIn(decision="approve"))
        if "cancel" in word or word in ("no", "n", "stop"):
            return family_decision(fam["id"], DecisionIn(decision="cancel"))
    return {"ignored": True}


@app.get("/api/cases/{transfer_id}/notes")
def case_notes(transfer_id: int):
    from . import agent
    return {"transfer_id": transfer_id, "notes": agent.read_notes(transfer_id)}


app.mount("/web", StaticFiles(directory="web", html=True), name="web")
