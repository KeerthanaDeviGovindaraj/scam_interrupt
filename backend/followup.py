"""Adaptive follow-up question.

classify() returns coached / calm / unclear. On "unclear" the pipeline asks ONE follow-up built from the
customer's own words, her bank data and the scam playbook it resembles; the second answer is judged
together with the first, and anything still unclear counts as coached (the family decides).
Model when MODEL is set; transparent rules otherwise or if the model fails.
"""
import json
import re

from . import coaching, config, playbooks

RELATION_WORDS = ["contractor", "landlord", "plumber", "electrician", "friend", "neighbor", "neighbour", "church",
                  "doctor", "dentist", "rent", "invoice", "every month", "agreed", "my daughter", "my son",
                  "my sister", "my brother", "my husband", "my wife", "license", "receipt", "met him", "met her",
                  "known him", "known her", "years", "monthly", "receipt", "treasurer", "brother-in-law",
                  "sister-in-law", "toured", "dentist", "bill", "moving company", "company", "will", "piano",
                  "in person", "insurance"]
FAMILY_WORDS = {"grandson": "your grandson", "granddaughter": "your granddaughter", "grandchild": "your grandchild",
                "nephew": "your nephew", "niece": "your niece", "son": "your son", "daughter": "your daughter"}
FORBIDDEN = ["password", "pin", "code", "account number", "social security number", "ssn"]

PROMPT = """You protect older bank customers from scams. A risky transfer was paused and the customer answered
a safety check. Decide: is the customer COACHED by a scammer, CALM (a believable, specific, ordinary reason),
or UNCLEAR (too vague to tell, e.g. a short reason with no link to the payee)?

coached: urgency or pressure, secrecy, defensive denial ("no one asked me"), a typical scam story
(bail, IRS, gift cards, crypto, "safe account", prize fees, an online partner needing money).
calm: names how they know the payee or a normal recurring purpose (rent to landlord, contractor they met).
unclear: anything else. Never call a vague answer calm.

Transfer: {transfer}
Risk reasons: {reasons}
{dialogue}

Reply with ONLY JSON:
{{"verdict": "coached" | "calm" | "unclear", "signals": ["short signal", ...],
  "scam_type": one of {types} or null, "explanation": "one plain sentence"}}"""

QUESTION_PROMPT = """You are a kind bank assistant talking to an older customer by text. A risky ${amount:,.0f}
transfer to {payee} (a new payee) is paused. Their answer was vague: "{answer}".
Write ONE short, warm follow-up question (max 2 sentences) built from their own words that a scammer could
not have scripted, e.g. asking how they know the payee or whether they called the person back on a number
they already had. {hint}
Never ask for passwords, codes, PINs or account numbers. Never accuse. Reply with only the question."""


def _text(out) -> str:
    return getattr(out, "text", None) or str(getattr(out, "content", out))


def _model():
    from langchain.chat_models import init_chat_model
    return init_chat_model(config.MODEL, temperature=0, timeout=20, max_retries=1)


def _mentions_relation(text: str, payee: str) -> bool:
    t = text.lower()
    names = [p.lower() for p in (payee or "").split() if len(p) > 2]
    return any(w in t for w in RELATION_WORDS) or any(n in t for n in names)


STRONG = ("urgency or pressure", "secrecy", "denies being contacted")
PRESSURE = ["hurry", "right now", "right away", "asap", "immediately", "please just", "quickly", "urgent",
            "no time", "don't have time", "before it's too late"]


def rule_classify(answer: str, transfer: dict, first_answer: str | None = None) -> dict:
    reasons = transfer.get("reasons") or []
    payee = transfer.get("payee_name", "")
    text = f"{first_answer or ''} {answer}".strip()
    base = coaching.rule_detect(answer, reasons)
    related = _mentions_relation(answer, payee)
    a = answer.lower()
    pressure = any(w in a for w in PRESSURE)                    # "today" alone is not pressure
    # Answering "no one contacted me" is what honest people say too: it only counts when the rest is vague.
    strong = pressure or "secrecy" in base["signals"] or ("denies being contacted" in base["signals"] and not related)
    story = any(s.startswith("story often used") for s in base["signals"])
    scam = playbooks.match(text)
    power = playbooks.strength(text)
    related = _mentions_relation(answer, payee)
    if first_answer is None:
        words = len(answer.split())
        names_payee = any(n.lower() in answer.lower() for n in payee.split() if len(n) > 2)
        vague = (words < 6 and not names_payee) or (not related and words < 14)
        if strong or power >= 2 or (story and not related):
            verdict = "coached"
        elif story or power >= 1 or vague:
            verdict = "unclear"
        else:
            verdict = "calm"
    else:  # second answer: anything still unclear counts as coached
        verdict = "coached" if (strong or story or power >= 1 or not related) else "calm"
    signals = [s for s in base["signals"] if verdict != "calm"]
    if scam and power >= 1 and verdict != "calm":
        signals.append(f"story matches a {playbooks.name(scam)}")
    if verdict == "coached" and first_answer is not None and not signals:
        signals.append("still could not explain the payment after a follow-up")
    return {"verdict": verdict, "signals": signals, "scam_type": scam if (power >= 1 or verdict == "unclear") else None,
            "detector": "rules",
            "explanation": "; ".join(signals) or ("Specific, ordinary reason." if verdict == "calm" else "Too vague to tell.")}


def classify(answer: str, transfer: dict, question: str = "", first_answer: str | None = None,
             follow_up_question: str | None = None) -> dict:
    rules = rule_classify(answer, transfer, first_answer)
    if not config.MODEL:
        return rules
    dialogue = f'Question: {question}\nAnswer: "{first_answer if first_answer is not None else answer}"'
    if first_answer is not None:
        dialogue += f'\nFollow-up question: {follow_up_question}\nSecond answer: "{answer}"\n' \
                    "This is the second answer: if it is still unclear, choose coached."
    try:
        out = _model().invoke(PROMPT.format(transfer=json.dumps({k: transfer.get(k) for k in ("amount", "payee_name", "hour")}),
                                            reasons=", ".join(transfer.get("reasons") or []), dialogue=dialogue,
                                            types=list(playbooks.PLAYBOOKS)))
        m = re.search(r"\{.*\}", _text(out), re.S)
        data = json.loads(m.group(0))
        verdict = str(data.get("verdict", "")).lower()
        if verdict not in ("coached", "calm", "unclear"):
            raise ValueError("bad verdict")
        if first_answer is not None and verdict == "unclear":
            verdict = "coached"
        if rules["verdict"] == "coached":          # safety net: rules never get overruled toward "calm"
            verdict = "coached"
        scam = data.get("scam_type") if data.get("scam_type") in playbooks.PLAYBOOKS else rules["scam_type"]
        signals = sorted(set([str(s) for s in data.get("signals", [])][:6]) | set(rules["signals"] if verdict == "coached" else []))
        return {"verdict": verdict, "signals": signals, "scam_type": scam, "detector": "llm",
                "explanation": str(data.get("explanation", ""))[:300]}
    except Exception as e:  # noqa: BLE001 - model trouble never blocks the check
        rules["explanation"] += f" (Model unavailable: {type(e).__name__}; used rules.)"
        return rules


def _relation(answer: str) -> str:
    t = answer.lower()
    return next((v for k, v in FAMILY_WORDS.items() if k in t), "them")


def question(answer: str, transfer: dict, first_name: str, scam_type: str | None) -> str:
    pb = playbooks.get(scam_type)
    template = pb["follow_up"].format(first=first_name, payee=transfer.get("payee_name", "this person"),
                                      relation=_relation(answer))
    if not config.MODEL:
        return template
    try:
        hint = f"The story resembles a {pb['name']}." if scam_type else ""
        q = _text(_model().invoke(QUESTION_PROMPT.format(amount=float(transfer.get("amount", 0)),
                                                         payee=transfer.get("payee_name", "the payee"),
                                                         answer=answer.replace('"', "'"), hint=hint))).strip().strip('"')
        if not q.endswith("?") or len(q) > 260 or any(w in q.lower() for w in FORBIDDEN):
            return template
        return f"Thanks, {first_name}. {q}" if not q.lower().startswith("thanks") else q
    except Exception:  # noqa: BLE001
        return template


def family_message(first_name: str, scam_type: str | None) -> str:
    pb = playbooks.get(scam_type)
    lead = f"This looks like a {pb['name']}." if scam_type else "This payment shows signs of a scam."
    return f"{lead} Nothing has been sent yet. {pb['family_ask'].format(first=first_name)}"


def customer_tip(scam_type: str | None) -> str:
    pb = playbooks.get(scam_type)
    return ("Why we paused this: it looked like a " + pb["name"] + ". " if scam_type else "") + pb["customer_tip"]
