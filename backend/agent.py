"""LangChain deepagents planner (AGENT_MODE=deepagents).

The planner receives one event plus the shared case JSON and decides which
tool runs next. The tools are the same functions the deterministic pipeline
uses, so both modes behave the same way. The Coaching Detector is a sub-agent.

VERIFY parameter names against the current deepagents docs
(create_deep_agent: model, tools, system_prompt, subagents). Turn on LangSmith
tracing (.env) so you can show judges the trace.
"""
import json

from . import config, pipeline

SYSTEM_PROMPT = """You are Scam Interrupt, an agent that protects bank customers, often older adults,
from scams. You receive one EVENT and the CASE (JSON). Decide the next step and call tools.

Rules:
- EVENT transfer_scored: if risk level is "high", call send_safety_check. Otherwise call
  release_transfer, then update_memory.
- EVENT customer_replied: call analyze_reply with the customer's answer (you may delegate the
  judgement to the coaching-detector sub-agent first). If coached is true, call alert_family.
  If false, call release_transfer, then update_memory.
- EVENT family_decided: handled by the app; do nothing.
- Never release a transfer that is awaiting a family decision.
- The customer always keeps the final say; you add a pause and a second voice, nothing more.
Finish with one short sentence describing what you did."""

COACHING_SUBAGENT = {
    "name": "coaching-detector",
    "description": "Judges whether a customer's safety-check answer shows signs of being coached by a scammer.",
    "system_prompt": ("Look for urgency, secrecy, denial of contact, a story that does not fit the payee or "
                      "amount, and scripted answers. Answer with JSON: "
                      '{"coached": bool, "signals": [..], "explanation": ".."}'),
    "tools": [],
}


# ----- tools (thin wrappers with docstrings the model can read) -----
def get_case(transfer_id: int) -> str:
    """Return the full case (transfer, customer, latest check, latest alert) as JSON."""
    return json.dumps(pipeline.get_case(transfer_id), default=str)


def send_safety_check(transfer_id: int) -> str:
    """Hold a risky transfer and send the customer a short safety-check question."""
    return json.dumps(pipeline.send_safety_check(transfer_id))


def analyze_reply(transfer_id: int, answer: str) -> str:
    """Run the Coaching Detector on the customer's answer and store the result."""
    return json.dumps(pipeline.analyze_reply(transfer_id, answer))


def alert_family(transfer_id: int) -> str:
    """Send the opted-in trusted contact an alert with Approve and Cancel options."""
    return json.dumps(pipeline.alert_family(transfer_id))


def release_transfer(transfer_id: int, note: str = "") -> str:
    """Send the transfer to Capital One Nessie. Only for low risk or after a passed check."""
    return json.dumps(pipeline.release_transfer(transfer_id, note))


def update_memory(customer_id: str) -> str:
    """Refresh the customer's normal spending habits."""
    return json.dumps(pipeline.update_memory(customer_id))


TOOLS = [get_case, send_safety_check, analyze_reply, alert_family, release_transfer, update_memory]
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        if not config.MODEL:
            raise RuntimeError("AGENT_MODE=deepagents needs MODEL set in .env")
        from deepagents import create_deep_agent
        _agent = create_deep_agent(model=config.MODEL, tools=TOOLS,
                                   system_prompt=SYSTEM_PROMPT, subagents=[COACHING_SUBAGENT])
    return _agent


def run(event: str, transfer_id: int, extra: dict | None = None) -> str:
    payload = {"event": event, "case": pipeline.get_case(transfer_id), **(extra or {})}
    result = get_agent().invoke({"messages": [{"role": "user", "content": json.dumps(payload, default=str)}]})
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    return getattr(msgs[-1], "content", "") if msgs else ""
