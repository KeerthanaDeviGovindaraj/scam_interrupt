"""Coaching Detector sub-agent.

Uses an LLM (MODEL in .env) that must return JSON. If no model is set, or the
model fails or returns bad JSON, it falls back to transparent rules, so the
demo never breaks.
"""
import json
import re

from . import config

URGENCY = ["hurry", "urgent", "right now", "right away", "asap", "quickly", "immediately", "today", "please just"]
SECRECY = ["don't tell", "dont tell", "do not tell", "not to tell", "secret", "keep this", "between us", "nobody needs to know"]
DENIAL = ["no one asked", "nobody asked", "no one contacted", "nobody contacted", "no one called", "nobody called",
          "my own idea", "i decided myself"]
STORY = ["bail", "jail", "school fees", "tuition", "irs", "taxes owed", "warrant", "lawyer", "hospital",
         "gift card", "bitcoin", "crypto", "safe account", "protect my money", "investment"]

PROMPT = """You protect older bank customers from scams. A risky transfer was held and the customer
answered a short safety check. Decide whether the customer is likely being COACHED by a scammer.

Signals of coaching: urgency or pressure, secrecy, denying anyone contacted them, a story that
does not fit the payee or amount (bail, fees, taxes, "safe account"), scripted or evasive answers.

Transfer: {transfer}
Risk reasons: {reasons}
Question asked: {question}
Customer's answer: {answer}

Reply with ONLY a JSON object, no other text:
{{"coached": true or false, "signals": ["short signal", ...], "explanation": "one plain sentence"}}"""


def rule_detect(answer: str, risk_reasons=None) -> dict:
    a = answer.lower()
    signals = []
    if any(w in a for w in URGENCY):
        signals.append("urgency or pressure")
    if any(w in a for w in SECRECY):
        signals.append("secrecy")
    if any(w in a for w in DENIAL):
        signals.append("denies being contacted")
    story = [w for w in STORY if w in a]
    if story:
        signals.append(f"story often used in scams ({story[0]})")
    if risk_reasons and "new payee" in risk_reasons and story:
        signals.append("story does not fit a brand-new payee")
    coached = len(signals) >= 2 or (len(signals) == 1 and len(risk_reasons or []) >= 3)
    expl = ("Answer shows " + ", ".join(signals) + ".") if signals else "Answer sounds calm and consistent."
    return {"coached": coached, "signals": signals, "explanation": expl, "detector": "rules"}


def _parse_json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    data = json.loads(m.group(0))
    if not isinstance(data.get("coached"), bool):
        raise ValueError("missing boolean 'coached'")
    data["signals"] = [str(s) for s in data.get("signals", [])][:6]
    data["explanation"] = str(data.get("explanation", ""))[:300]
    return data


def llm_detect(answer: str, question: str, transfer: dict, risk_reasons) -> dict:
    from langchain.chat_models import init_chat_model  # imported lazily
    model = init_chat_model(config.MODEL, temperature=0, timeout=20, max_retries=1)
    msg = PROMPT.format(transfer=json.dumps(transfer), reasons=", ".join(risk_reasons or []),
                        question=question, answer=answer)
    out = model.invoke(msg)
    data = _parse_json(getattr(out, "text", None) or str(getattr(out, "content", out)))
    data["detector"] = "llm"
    return data


def detect(answer: str, question: str = "", transfer: dict = None, risk_reasons=None) -> dict:
    if config.MODEL:
        try:
            result = llm_detect(answer, question, transfer or {}, risk_reasons)
            # Safety net: if rules see strong coaching the model missed, keep the hold.
            rules = rule_detect(answer, risk_reasons)
            if rules["coached"] and not result["coached"]:
                result["coached"] = True
                result["signals"] = sorted(set(result["signals"]) | set(rules["signals"]))
                result["explanation"] += " (Rule check also flagged coaching.)"
            return result
        except Exception as e:  # noqa: BLE001 - fall back on any model problem
            r = rule_detect(answer, risk_reasons)
            r["explanation"] += f" (Model unavailable: {type(e).__name__}; used rules.)"
            return r
    return rule_detect(answer, risk_reasons)
