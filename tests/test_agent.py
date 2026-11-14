"""Tests the deepagents wiring with a fake agent (no model, no network).
Run:  python -m tests.test_agent"""
import json
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({"NESSIE_MODE": "mock", "PHOTON_MODE": "sim", "MODEL": "", "AGENT_MODE": "deepagents", "AGENT_BACKGROUND": "false",
                   "DB_PATH": os.path.join(_tmp, "a.db"), "MOCK_NESSIE_PATH": os.path.join(_tmp, "n.json")})

from backend import agent, db, pipeline  # noqa: E402
from backend.seed import seed  # noqa: E402


class FakeAgent:
    calls = []

    """Behaves like the planner + sub-agents: calls the same tools in the same order."""

    def invoke(self, inputs, config=None):
        p = json.loads(inputs["messages"][0]["content"])
        tid = p["transfer_id"]
        FakeAgent.calls.append((p["event"], p.get("mode")))
        if p.get("mode") == "review":
            with open(agent.notes_path(tid), "a") as f:
                f.write("\n## Agent review\nAgree with the app's action.\n")
            return {"messages": [type("M", (), {"text": "reviewed", "content": "reviewed"})()]}
        if p["event"] == "transfer_scored":
            agent.get_case(tid)
            with open(agent.notes_path(tid), "a") as f:
                f.write("\n## Risk analysis\nNew payee, far above usual amount, late at night.\n")
            agent.send_safety_check(tid)
        elif p["event"] == "customer_replied":
            verdict = json.loads(agent.analyze_reply(tid, p["answer"]))
            if verdict["coached"]:
                agent.alert_family(tid, "Mary is about to send money to someone new. Nothing has been sent yet.")
            else:
                agent.release_transfer(tid, "Safety check passed.")
        return {"messages": [type("M", (), {"text": "done", "content": "done"})()]}


agent._agent = FakeAgent()


def _ray():
    seed(reset=True)
    return db.q1("SELECT nessie_account_id FROM customers WHERE id='ray'")["nessie_account_id"]


def test_agent_scam_flow_and_notes():
    ray = _ray()
    s = pipeline.create_and_score(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                  payee_kind="account", amount=3000, hour=23)
    agent.run("transfer_scored", s["transfer_id"])
    assert pipeline.get_case(s["transfer_id"])["transfer"]["status"] == "awaiting_customer"
    agent.run("customer_replied", s["transfer_id"], {"answer": "No one asked me. It's for school fees. Please hurry."})
    case = pipeline.get_case(s["transfer_id"])
    assert case["transfer"]["status"] == "awaiting_family"
    assert "Nothing has been sent yet" in case["alert"]["message"]
    notes = agent.read_notes(s["transfer_id"])
    assert "Risk analysis" in notes and "Outcome after customer_replied" in notes
    assert os.path.exists(os.path.join(agent.FS_ROOT, "customers", "mary", "profile.md"))


def test_low_risk_skips_agent():
    seed(reset=True)
    david = db.q1("SELECT nessie_account_id FROM customers WHERE id='david'")["nessie_account_id"]
    s = pipeline.create_and_score(customer_id="mary", payee_id=david, payee_name="David Lee",
                                  payee_kind="account", amount=120, hour=14)
    agent.run("transfer_scored", s["transfer_id"])
    assert pipeline.get_case(s["transfer_id"])["transfer"]["status"] == "released"


def test_guardrails():
    ray = _ray()
    s = pipeline.create_and_score(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                  payee_kind="account", amount=3000, hour=23)
    tid = s["transfer_id"]
    assert "refused" in agent.release_transfer(tid)            # high risk, no check yet
    assert "refused" in agent.alert_family(tid)                # no coaching verdict yet
    agent.send_safety_check(tid)
    agent.analyze_reply(tid, "Hurry, it's urgent and secret")
    assert "refused" in agent.release_transfer(tid)            # coached -> family must decide
    agent.alert_family(tid)
    assert "refused" in agent.release_transfer(tid)            # awaiting family


def test_background_fast_mode():
    from backend import config
    config.AGENT_BACKGROUND = True
    try:
        ray = _ray()
        s = pipeline.create_and_score(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                      payee_kind="account", amount=3000, hour=23)
        tid = s["transfer_id"]
        agent.run("transfer_scored", tid)
        assert pipeline.get_case(tid)["transfer"]["status"] == "awaiting_customer"   # instant
        agent._last_thread.join(5)
        agent.run("customer_replied", tid, {"answer": "No one asked me. It's for school fees. Please hurry."})
        assert pipeline.get_case(tid)["transfer"]["status"] == "awaiting_family"     # instant
        agent._last_thread.join(5)
        notes = agent.read_notes(tid)
        assert notes.count("## Agent review") == 2 and "customer_replied-review" in notes
        assert ("customer_replied", "review") in FakeAgent.calls
    finally:
        config.AGENT_BACKGROUND = False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
