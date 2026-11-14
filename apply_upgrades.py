"""Wire the four upgrades into the existing files. Safe to run more than once.

    python apply_upgrades.py

Prints changed / already done / NOT FOUND for every edit. NOT FOUND means that part of your
file differs from what we expected: paste the line here and we'll adjust by hand.
"""
import re

RESULTS = []


def patch(path, edits):
    s = open(path).read()
    for label, old, new in edits:
        if new in s:
            RESULTS.append(("already done", path, label))
        elif old in s:
            s = s.replace(old, new, 1)
            RESULTS.append(("changed", path, label))
        else:
            RESULTS.append(("NOT FOUND", path, label))
    open(path, "w").write(s)


# ---------------- config ----------------
patch("backend/config.py", [
    ("upgrade settings", "# Risk thresholds", '''# Upgrades
FOLLOW_UP = env("FOLLOW_UP", "true").lower() in ("1", "true", "yes")      # adaptive follow-up question
NESSIE_HOLD = env("NESSIE_HOLD", "app").lower()                           # app | hook (Nessie decision hooks)
NESSIE_HOOK_SECRET = env("NESSIE_HOOK_SECRET")
PUBLIC_URL = env("PUBLIC_URL")                                             # e.g. https://abc.ngrok-free.app

# Risk thresholds'''),
])

# ---------------- db: new columns ----------------
patch("backend/db.py", [
    ("migrations", '''def init_db():
    with connect() as c:
        c.executescript(SCHEMA)''', '''MIGRATIONS = [
    "ALTER TABLE checks ADD COLUMN followup_question TEXT",
    "ALTER TABLE checks ADD COLUMN followup_answer TEXT",
    "ALTER TABLE checks ADD COLUMN scam_type TEXT",
    "ALTER TABLE transfers ADD COLUMN scam_type TEXT",
]


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)
        for m in MIGRATIONS:
            try:
                c.execute(m)
            except sqlite3.OperationalError:
                pass  # column already exists'''),
])

# ---------------- nessie client ----------------
patch("backend/nessie.py", [
    ("live: decisions + webhooks", "\n\nclass MockNessie:", '''
    # ----- decisions and webhooks (Nessie v2) -----
    def decide(self, tx_id, decision, reason=""):
        return self._req("POST", f"/transactions/{tx_id}/decision", {"decision": decision, "reason": (reason or "")[:200]})

    def get_transaction(self, tx_id):
        return self._req("GET", f"/transactions/{tx_id}")

    def list_webhooks(self):
        return _items(self._req("GET", "/webhooks"))

    def create_webhook(self, body):
        return self._req("POST", "/webhooks", body)

    def delete_webhook(self, hook_id):
        return self._req("DELETE", f"/webhooks/{hook_id}")


class MockNessie:'''),
    ("mock: decisions", "\n\n_client = None", '''

    def decide(self, tx_id, decision, reason=""):
        d = self._load(); d.setdefault("decisions", []).append({"tx": tx_id, "decision": decision, "reason": reason})
        self._save(d)
        return {"id": tx_id, "decision": decision}

    def list_webhooks(self):
        return []

    def create_webhook(self, body):
        return {"id": "hook_mock", "secret": "mock_secret", **body}

    def delete_webhook(self, hook_id):
        return {}


_client = None'''),
])

# ---------------- pipeline ----------------
patch("backend/pipeline.py", [
    ("imports", "from . import coaching, db, memory, messaging, risk",
     "from . import coaching, config, db, followup, memory, messaging, nessie_hooks, playbooks, risk"),
    ("hook: open transfer in Nessie", "def watchlist_hits(payee_id: str) -> int:", '''def _open_in_nessie(transfer_id: int) -> None:
    """Hook mode: create the transfer in Nessie now; the bank holds it until we decide."""
    t = db.q1("SELECT * FROM transfers WHERE id=?", (transfer_id,))
    acct = db.q1("SELECT nessie_account_id FROM customers WHERE id=?", (t["customer_id"],))["nessie_account_id"]
    try:
        obj = get_nessie().create_transfer(acct, t["payee_id"], t["amount"], f"Scam Interrupt #{transfer_id}")
        _set(transfer_id, nessie_ref=str(obj.get("id") or obj.get("_id") or ""))
    except Exception as e:  # noqa: BLE001 - e.g. insufficient funds; fall back to holding in our app
        _set(transfer_id, note=f"Nessie: {str(e)[:180]}")


def watchlist_hits(payee_id: str) -> int:'''),
    ("hook: create on request", '''                 r["score"], r["level"], json.dumps(r["reasons"]), db.now(), db.now()))
    return {"transfer_id": tid, **r}''', '''                 r["score"], r["level"], json.dumps(r["reasons"]), db.now(), db.now()))
    if config.NESSIE_HOLD == "hook" and payee_kind == "account":
        _open_in_nessie(tid)
    return {"transfer_id": tid, **r}'''),
    ("hook: approve on release", '''    n = get_nessie()
    if t["payee_kind"] == "merchant":''', '''    if config.NESSIE_HOLD == "hook" and t.get("nessie_ref") and t["payee_kind"] == "account":
        if nessie_hooks.approve(t["nessie_ref"], note):
            _set(transfer_id, status="released", note=note)
            return {"status": "released", "nessie_ref": t["nessie_ref"]}
        # the bank's decision window closed (e.g. declined after 5 minutes): send a fresh transfer
    n = get_nessie()
    if t["payee_kind"] == "merchant":'''),
    ("hook: decline on cancel", '''    """Cancel a held transfer. Nothing is ever sent to Nessie."""
    _set(transfer_id, status="cancelled", note=note)''', '''    """Cancel a held transfer. App mode: nothing reaches Nessie. Hook mode: the bank declines it."""
    _set(transfer_id, status="cancelled", note=note)
    t = db.q1("SELECT nessie_ref FROM transfers WHERE id=?", (transfer_id,))
    if config.NESSIE_HOLD == "hook" and t and t.get("nessie_ref"):
        nessie_hooks.decline(t["nessie_ref"], note)'''),
    ("handle_reply", "def on_transfer_requested(**kw) -> dict:", '''def _first(customer_id: str) -> str:
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
                  (answer, (chk.get("transcript") or "") + "\\n" + answer, json.dumps(r["signals"]),
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


def on_transfer_requested(**kw) -> dict:'''),
    ("on_customer_reply uses handle_reply", '''    result = analyze_reply(transfer_id, answer)
    if result["coached"]:
        alert_family(transfer_id)
    else:
        release_transfer(transfer_id, "Safety check passed.")
        messaging.send(t["customer_id"], "Thank you. Your payment has been sent. "
                                         "Remember: we'll never ask you to keep a payment secret.", transfer_id)
        update_memory(t["customer_id"])
    return get_case(transfer_id)''', '''    handle_reply(transfer_id, answer)
    return get_case(transfer_id)'''),
    ("teach after cancel", '''        messaging.send(alert["contact_id"], f"Done: ${t['amount']:,.0f} stayed in the account.", transfer_id)''',
     '''        messaging.send(alert["contact_id"], f"Done: ${t['amount']:,.0f} stayed in the account.", transfer_id)
        chk = get_case(transfer_id)["check"] or {}
        messaging.send(t["customer_id"], followup.customer_tip(chk.get("scam_type")), transfer_id)'''),
])

# ---------------- agent ----------------
s = open("backend/agent.py").read()
m = re.search(r"def _fast_reply\(transfer_id: int, answer: str\) -> None:.*?\n\n\n(?=def )", s, re.S)
new_fast = '''def _fast_reply(transfer_id: int, answer: str) -> None:
    """Instant, proven path: judge the reply, ask one follow-up if unclear, then alert family or release."""
    pipeline.handle_reply(transfer_id, answer)


'''
if "pipeline.handle_reply(transfer_id, answer)" in s:
    RESULTS.append(("already done", "backend/agent.py", "_fast_reply"))
elif m:
    s = s[:m.start()] + new_fast + s[m.end():]
    RESULTS.append(("changed", "backend/agent.py", "_fast_reply"))
else:
    RESULTS.append(("NOT FOUND", "backend/agent.py", "_fast_reply"))
open("backend/agent.py", "w").write(s)
patch("backend/agent.py", [
    ("import playbooks", "from . import config, db, memory, pipeline", "from . import config, db, memory, pipeline, playbooks"),
    ("playbooks in prompt", "2. Read /customers/<customer_id>/profile.md and /cases/<transfer_id>/notes.md.",
     "2. Read /customers/<customer_id>/profile.md and /cases/<transfer_id>/notes.md. Scam playbooks are in\n"
     "   /playbooks/ (one file per scam type): if the case check has a scam_type, read that playbook and\n"
     "   name the scam in your notes. If a follow-up question was asked, delegate to the interviewer."),
    ("write playbook files", '''    profile = write_profile(t["customer_id"])
    ensure_notes(transfer_id)
    payload''', '''    profile = write_profile(t["customer_id"])
    ensure_notes(transfer_id)
    playbooks.write_files(FS_ROOT)
    payload'''),
    ("interviewer sub-agent", "SUBAGENTS = [", '''SUBAGENTS = [
    {"name": "interviewer", "description": "Reviews the adaptive follow-up: the question asked, both answers, and "
     "whether the follow-up revealed coaching. Give it the transfer_id.",
     "system_prompt": ("You are the interviewer. Call get_case. The check has the first answer, the follow-up "
                       "question and the second answer. In 2-3 sentences say what the follow-up revealed and why it "
                       "was hard for a scammer to script. Call append_note(transfer_id, \\"Follow-up review\\", ...). "
                       "Only call tools you have been given."),
     "tools": [get_case, append_note]},'''),
])

# ---------------- app ----------------
patch("backend/app.py", [
    ("nessie hook route", 'app.mount("/web"', '''from .nessie_hooks import router as nessie_router  # noqa: E402
if nessie_router is not None:
    app.include_router(nessie_router)


app.mount("/web"'''),
    ("agent fallback knows follow-ups", '''        if t["status"] == "awaiting_customer":  # agent did nothing useful -> fixed flow''',
     '''        if t["status"] == "awaiting_customer" and not pipeline.awaiting_followup(transfer_id):  # agent did nothing -> fixed flow'''),
])

# ---------------- .env.example ----------------
patch(".env.example", [
    ("env vars", "# ---- Demo phone numbers", '''# ---- Upgrades ----
FOLLOW_UP=true
# app = our app holds risky transfers; hook = Nessie holds them and asks us (decision hooks)
NESSIE_HOLD=app
NESSIE_HOOK_SECRET=
PUBLIC_URL=

# ---- Demo phone numbers'''),
])

for status, path, label in RESULTS:
    print(f"{status:13} {path:24} {label}")
bad = [r for r in RESULTS if r[0] == "NOT FOUND"]
print("\nAll good." if not bad else f"\n{len(bad)} edit(s) need attention: paste these lines to Claude.")
