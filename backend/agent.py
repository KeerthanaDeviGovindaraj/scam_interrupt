"""LangChain deepagents planner for Scam Interrupt (AGENT_MODE=deepagents).

How it uses Deep Agents
- Planner: receives one EVENT, writes a plan with the built-in to-do tool, then acts.
- Sub-agents (delegated with the built-in `task` tool):
    risk-analyst      explains why the transfer is risky, from the case and the customer's profile
    coaching-detector runs the authoritative coaching check on the customer's reply and interprets it
    family-messenger  writes a short, calm alert and sends it to the opted-in trusted contact
- File system as a case notebook (real files under data/agent_fs/, shown in the demo):
    /customers/<id>/profile.md     written by the app before every run (habits, trusted contact, history)
    /cases/<transfer_id>/notes.md  the agents append what they checked, the answer, signals, decision, why
- Guardrails: money-moving tools refuse unsafe actions (e.g. releasing while a family decision is pending).

If anything here fails, backend/app.py falls back to the fixed pipeline, so the demo never breaks.
VERIFY against the installed deepagents version if an import or parameter name differs.
"""
import json
import logging
import os
import threading

from . import config, db, memory, pipeline, playbooks

log = logging.getLogger("agent")
FS_ROOT = os.path.join(os.path.dirname(config.DB_PATH) or "data", "agent_fs")

PLANNER_PROMPT = """You are Scam Interrupt, an agent that protects bank customers, often older adults, from scams.
You get one EVENT and a transfer_id. Work like this:

1. Call record_plan(transfer_id, steps) with 3-5 short steps for this event.
2. Read /customers/<customer_id>/profile.md and /cases/<transfer_id>/notes.md. Scam playbooks are in
   /playbooks/ (one file per scam type): if the case check has a scam_type, read that playbook and
   name the scam in your notes. If a follow-up question was asked, delegate to the interviewer.
3. Follow the rules for the event:
   - EVENT transfer_scored (risk is high): delegate to the risk-analyst sub-agent to explain the risk and
     append a "## Risk analysis" section to the case notes. Then call send_safety_check.
   - EVENT customer_replied: delegate to the coaching-detector sub-agent with the transfer_id and the exact
     answer. If it reports coached = true, delegate to the family-messenger sub-agent to alert the family.
     If coached = false, call release_transfer with a short note, then update_memory.
4. Call append_note(transfer_id, "Decision", ...): what you did and why, in plain English.

REVIEW MODE: if the payload has "mode": "review", the app has ALREADY acted for speed (the safety check
was sent, or the reply was judged and the family alerted or the payment released). Do NOT call send_safety_check
or release_transfer. Instead: plan with record_plan, read the profile and case notes, call get_case, delegate to
risk-analyst (for transfer_scored) or coaching-detector (for customer_replied) to review and document, then
call append_note(transfer_id, "Agent review", ...) saying whether you agree with what the app did and why.
To add to the case notes, ALWAYS use append_note; never write or edit the notes file directly.

Sub-agents write their own notes: never re-append what a sub-agent returned.
Rules: only call tools you have been given. Never release a transfer that is waiting for a family decision. The customer always keeps the final
say; you only add a pause and a second voice. Finish with one short sentence describing what you did."""

RISK_ANALYST_PROMPT = """You are the risk analyst. You receive a transfer_id.
Call get_case, read /customers/<customer_id>/profile.md, and explain in 2-4 plain sentences why this
transfer looks risky compared with the customer's normal habits (payee, amount vs usual, time, merchant).
If the case has a safety check, quote its stored signals exactly; do not guess what the customer said.
Call append_note(transfer_id, "Risk analysis", your explanation). Never edit the notes file directly.
Return the explanation.
Only call tools you have been given."""

COACHING_PROMPT = """You are the coaching detector. You receive a transfer_id and the customer's exact answer.
First call get_case. If the case's check already has a verdict ("coached" is 0 or 1), do NOT call analyze_reply:
review that verdict instead. Otherwise call analyze_reply(transfer_id, answer) exactly once: it runs the
authoritative check (model + rule safety net).
Then call append_note(transfer_id, "Safety check", ...) with the answer, the signals and the verdict.
Never edit the notes file directly. Return a JSON object: {"coached": true|false, "signals": [...], "explanation": "..."}.
Only call tools you have been given."""

FAMILY_PROMPT = """You are the family messenger. You receive a transfer_id.
Call get_case, then write a short, calm message (max 3 sentences) to the trusted contact: what is happening,
that nothing has been sent yet, and that they should call the customer before deciding. No jargon, no panic.
Call alert_family(transfer_id, message). Then call append_note(transfer_id, "Family alert", your message).
Return "sent".
Only call tools you have been given."""


# ---------------- tools ----------------
def get_case(transfer_id: int) -> str:
    """Return the case (transfer, customer, latest check, latest alert) as JSON."""
    return json.dumps(pipeline.get_case(int(transfer_id)), default=str)


def send_safety_check(transfer_id: int) -> str:
    """Hold a risky transfer and send the customer a short safety-check question."""
    t = pipeline.get_case(int(transfer_id))["transfer"]
    if t["status"] != "scoring":
        return json.dumps({"refused": f"transfer is already {t['status']}"})
    return json.dumps(pipeline.send_safety_check(int(transfer_id)))


def analyze_reply(transfer_id: int, answer: str) -> str:
    """Run the Coaching Detector (LLM + rules safety net) on the customer's answer and store the verdict."""
    t = pipeline.get_case(int(transfer_id))["transfer"]
    if t["status"] != "awaiting_customer":
        return json.dumps({"refused": f"transfer is {t['status']}, not waiting for the customer"})
    return json.dumps(pipeline.analyze_reply(int(transfer_id), answer))


def alert_family(transfer_id: int, message: str = "") -> str:
    """Send the opted-in trusted contact an alert with Approve / Cancel. `message` is your calm wording."""
    case = pipeline.get_case(int(transfer_id))
    if not (case["check"] and case["check"].get("coached") == 1):
        return json.dumps({"refused": "only alert family after the coaching check says coached"})
    if case["transfer"]["status"] != "awaiting_customer":
        return json.dumps({"refused": f"transfer is {case['transfer']['status']}"})
    return json.dumps(pipeline.alert_family(int(transfer_id), message))


def release_transfer(transfer_id: int, note: str = "") -> str:
    """Send the transfer to Capital One Nessie. Only for low risk or after a passed safety check."""
    case = pipeline.get_case(int(transfer_id))
    status, chk = case["transfer"]["status"], case["check"]
    if status in ("awaiting_family", "held_review", "cancelled"):
        return json.dumps({"refused": f"cannot release while {status}"})
    if chk and chk.get("coached") == 1:
        return json.dumps({"refused": "coaching was detected; the family must decide"})
    if case["transfer"]["risk_level"] == "high" and not (chk and chk.get("coached") == 0):
        return json.dumps({"refused": "high-risk transfer needs a passed safety check first"})
    return json.dumps(pipeline.release_transfer(int(transfer_id), note))


def record_plan(transfer_id: int, steps: list[str]) -> str:
    """Write your short plan (3-5 steps) into the case notes before acting."""
    ensure_notes(int(transfer_id))
    with open(notes_path(int(transfer_id)), "a") as f:
        f.write("\n## Plan\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(steps, 1)) + "\n")
    return "plan recorded"


def write_todos(content: str = "", todos: list | None = None, file_path: str = "") -> str:
    """Write your plan / to-do list for the current case (same as record_plan)."""
    tid = getattr(_current, "transfer_id", None)
    items = [str(x.get("content", x)) if isinstance(x, dict) else str(x) for x in (todos or [])]
    if content:
        items += [ln.strip("-* ").strip() for ln in str(content).splitlines() if ln.strip("-* ").strip()]
    if tid is None or not items:
        return "todos noted"
    return record_plan(tid, items[:8])


def append_note(transfer_id: int, section: str, text: str) -> str:
    """Add a section to the END of the case notes. Use this for every note you write."""
    ensure_notes(int(transfer_id))
    title = str(section).strip().lstrip("#").strip() or "Note"
    lines = str(text).strip().splitlines()
    while lines and lines[0].strip().lstrip("#").strip().lower() in (title.lower(), ""):
        lines.pop(0)                      # drop a repeated heading the model put in the text
    body = "\n".join(lines).strip()
    if not body:
        return "note skipped (empty)"
    current = read_notes(int(transfer_id))
    if body in current:
        return "note already present"     # sub-agent already wrote it
    with open(notes_path(int(transfer_id)), "a") as f:
        f.write(f"\n## {title}\n{body}\n")
    return "note added"


def update_memory(customer_id: str) -> str:
    """Refresh the customer's normal spending habits."""
    return json.dumps(pipeline.update_memory(customer_id))


MAIN_TOOLS = [record_plan, write_todos, append_note, get_case, send_safety_check, release_transfer, update_memory]
SUBAGENTS = [
    {"name": "interviewer", "description": "Reviews the adaptive follow-up: the question asked, both answers, and "
     "whether the follow-up revealed coaching. Give it the transfer_id.",
     "system_prompt": ("You are the interviewer. Call get_case. The check has the first answer, the follow-up "
                       "question and the second answer. In 2-3 sentences say what the follow-up revealed and why it "
                       "was hard for a scammer to script. Call append_note(transfer_id, \"Follow-up review\", ...). "
                       "Only call tools you have been given."),
     "tools": [get_case, append_note]},
    {"name": "risk-analyst", "description": "Explains why a transfer is risky using the case and the customer's profile; "
     "writes the Risk analysis section of the case notes.", "system_prompt": RISK_ANALYST_PROMPT, "tools": [get_case, write_todos, append_note]},
    {"name": "coaching-detector", "description": "Judges the customer's safety-check answer for scammer coaching and "
     "records the verdict. Give it the transfer_id and the exact answer.", "system_prompt": COACHING_PROMPT,
     "tools": [get_case, analyze_reply, write_todos, append_note]},
    {"name": "family-messenger", "description": "Writes a calm alert and sends it to the opted-in trusted contact. "
     "Give it the transfer_id.", "system_prompt": FAMILY_PROMPT, "tools": [get_case, alert_family, write_todos, append_note]},
]


# ---------------- case notebook (real files) ----------------
def _path(*parts) -> str:
    p = os.path.join(FS_ROOT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def write_profile(customer_id: str) -> str:
    c = db.q1("SELECT * FROM customers WHERE id=?", (customer_id,))
    h = memory.get_habits(customer_id)
    contact = db.q1("SELECT name FROM customers WHERE id=?", (c["trusted_contact_id"],)) if c["trusted_contact_id"] else None
    past = db.q("SELECT id, payee_name, amount, status FROM transfers WHERE customer_id=? ORDER BY id DESC LIMIT 5",
                (customer_id,))
    lines = [f"# Customer profile: {c['name']}", "",
             f"- Usual payment size: about ${h['avg_amount']:,.0f} (largest recent: ${h['max_amount']:,.0f})",
             f"- Known payees: {len(h['usual_payees'])}",
             f"- Usual active hours: {min(h['active_hours'])}:00 to {max(h['active_hours'])}:00",
             f"- Trusted contact: {contact['name'] if contact else 'none'} "
             f"({'opted in' if c['family_opt_in'] else 'not opted in'})", "", "## Recent transfers"]
    lines += [f"- #{p['id']} ${p['amount']:,.0f} to {p['payee_name']}: {p['status']}" for p in past] or ["- none"]
    text = "\n".join(lines) + "\n"
    with open(_path("customers", customer_id, "profile.md"), "w") as f:
        f.write(text)
    return text


def notes_path(transfer_id: int) -> str:
    return _path("cases", str(transfer_id), "notes.md")


def ensure_notes(transfer_id: int) -> None:
    p = notes_path(transfer_id)
    if not os.path.exists(p):
        t = pipeline.get_case(transfer_id)["transfer"]
        with open(p, "w") as f:
            f.write(f"# Case {transfer_id}: ${t['amount']:,.0f} to {t['payee_name']}\n\n"
                    f"- Risk: {t['risk_level']} ({t['risk_score']}) - {', '.join(t['reasons']) or 'no flags'}\n\n")


def append_outcome(transfer_id: int, event: str, summary: str) -> None:
    t = pipeline.get_case(transfer_id)["transfer"]
    with open(notes_path(transfer_id), "a") as f:
        f.write(f"\n## Outcome after {event}\n- Status: {t['status']}\n- Agent summary: {summary or '(none)'}\n")


def read_notes(transfer_id: int) -> str:
    p = notes_path(transfer_id)
    return open(p).read() if os.path.exists(p) else ""


# ---------------- agent ----------------
_agent = None


def _backend():
    """Real-disk file system so case notes survive and can be shown. Falls back to the default (in-state)."""
    try:
        from deepagents.backends import FilesystemBackend
        try:
            return FilesystemBackend(root_dir=FS_ROOT, virtual_mode=True)
        except TypeError:
            return FilesystemBackend(root_dir=FS_ROOT)
    except Exception as e:  # noqa: BLE001
        log.warning("FilesystemBackend unavailable (%s); using in-state files", e)
        return None


def get_agent():
    global _agent
    if _agent is None:
        if not config.MODEL:
            raise RuntimeError("AGENT_MODE=deepagents needs MODEL set in .env")
        from deepagents import create_deep_agent
        from langchain.chat_models import init_chat_model
        model = init_chat_model(config.AGENT_MODEL, temperature=0, timeout=60, max_retries=6)
        kwargs = dict(model=model, tools=MAIN_TOOLS, system_prompt=PLANNER_PROMPT, subagents=SUBAGENTS)
        backend = _backend()
        if backend is not None:
            kwargs["backend"] = backend
        try:
            _agent = create_deep_agent(**kwargs)
        except TypeError:          # older versions: no backend parameter
            kwargs.pop("backend", None)
            _agent = create_deep_agent(**kwargs)
    return _agent


def _save_state_files(result) -> None:
    """If the agent used in-state files, copy them to disk so the demo can show them."""
    files = result.get("files") if isinstance(result, dict) else None
    for path, data in (files or {}).items():
        content = data if isinstance(data, str) else "\n".join(data.get("content", [])) if isinstance(data, dict) else ""
        if content and path.startswith("/cases/"):
            with open(_path(*path.strip("/").split("/")), "w") as f:
                f.write(content)


_current = threading.local()   # which case the running agent is working on
_review_lock = threading.Lock()   # one background review at a time keeps us under rate limits
_last_thread = None


def _fast_reply(transfer_id: int, answer: str) -> None:
    """Instant, proven path: judge the reply, ask one follow-up if unclear, then alert family or release."""
    pipeline.handle_reply(transfer_id, answer)


def _invoke(event: str, transfer_id: int, extra: dict | None = None, review: bool = False) -> str:
    _current.transfer_id = transfer_id
    t = pipeline.get_case(transfer_id)["transfer"]
    profile = write_profile(t["customer_id"])
    ensure_notes(transfer_id)
    playbooks.write_files(FS_ROOT)
    payload = {"event": event, "transfer_id": transfer_id, "customer_id": t["customer_id"], **(extra or {})}
    if review:
        payload["mode"] = "review"
    inputs = {"messages": [{"role": "user", "content": json.dumps(payload, default=str)}]}
    if _backend() is None:  # in-state files: hand the agent its notebook
        inputs["files"] = {f"/customers/{t['customer_id']}/profile.md": profile,
                           f"/cases/{transfer_id}/notes.md": read_notes(transfer_id)}
    tag = f"{event}{'-review' if review else ''}"
    result = get_agent().invoke(inputs, config={"recursion_limit": 80, "run_name": f"scam-interrupt:{tag}",
                                                "tags": ["scam-interrupt", tag]})
    _save_state_files(result)
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    last = msgs[-1] if msgs else None
    summary = (getattr(last, "text", None) or getattr(last, "content", "") or "") if last else ""
    append_outcome(transfer_id, tag, str(summary)[:500])
    return str(summary)


def _review(event: str, transfer_id: int, extra: dict | None) -> None:
    with _review_lock:
        try:
            _invoke(event, transfer_id, extra, review=True)
        except Exception as e:  # noqa: BLE001 - a failed review never affects the customer
            log.warning("background agent review failed: %s", e)
            try:
                with open(notes_path(transfer_id), "a") as f:
                    f.write(f"\n## Agent review unavailable\n- {type(e).__name__}: {str(e)[:200]}\n")
            except OSError:
                pass


def run(event: str, transfer_id: int, extra: dict | None = None) -> str:
    global _last_thread
    t = pipeline.get_case(transfer_id)["transfer"]
    if event == "transfer_scored" and t["risk_level"] != "high":
        # Normal payments never wait on the agent: release straight away.
        pipeline.release_transfer(transfer_id, "Normal payment, no interruption.")
        pipeline.update_memory(t["customer_id"])
        return "Low risk: released without interruption."
    if not config.AGENT_BACKGROUND:
        return _invoke(event, transfer_id, extra)
    # Fast mode: act instantly, then let the deepagents planner review and document in the background.
    ensure_notes(transfer_id)
    if event == "transfer_scored" and t["status"] == "scoring":
        pipeline.send_safety_check(transfer_id)
    elif event == "customer_replied":
        _fast_reply(transfer_id, (extra or {}).get("answer", ""))
    _last_thread = threading.Thread(target=_review, args=(event, transfer_id, extra), daemon=True)
    _last_thread.start()
    return "Acted instantly; agent review running in the background."
