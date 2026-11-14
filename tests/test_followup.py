"""Adaptive follow-up question + scam playbooks (offline, rules only).
Run:  python -m tests.test_followup"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({"NESSIE_MODE": "mock", "PHOTON_MODE": "sim", "MODEL": "", "FOLLOW_UP": "true",
                   "DB_PATH": os.path.join(_tmp, "f.db"), "MOCK_NESSIE_PATH": os.path.join(_tmp, "n.json")})

from backend import config, db, followup, messaging, pipeline, playbooks  # noqa: E402
from backend.seed import seed  # noqa: E402


def _scam_case():
    seed(reset=True)
    ray = db.q1("SELECT nessie_account_id FROM customers WHERE id='ray'")["nessie_account_id"]
    case = pipeline.on_transfer_requested(customer_id="mary", payee_id=ray, payee_name="Ray Collins",
                                          payee_kind="account", amount=3000, hour=23)
    return case["transfer"]["id"]


def _last(owner):
    return messaging.inbox(owner)[-1]["text"]


def test_vague_answer_gets_one_follow_up_then_family():
    tid = _scam_case()
    case = pipeline.on_customer_reply(tid, "It's for my grandson.")
    assert case["transfer"]["status"] == "awaiting_customer"            # still waiting: one more question
    q = case["check"]["followup_question"]
    assert q and q.endswith("?") and "grandson" in q.lower(), q
    assert _last("mary") == q                                            # asked in the same thread
    case = pipeline.on_customer_reply(tid, "He called from a new number and said not to tell his mom. Ray is his lawyer.")
    assert case["transfer"]["status"] == "awaiting_family"
    assert case["check"]["coached"] == 1 and case["check"]["scam_type"] == "grandparent"
    assert "grandparent emergency scam" in case["alert"]["message"]
    assert "usual number" in case["alert"]["message"]                   # tells David what to ask
    assert case["transfer"]["scam_type"] == "grandparent emergency scam"
    pipeline.on_family_decision(tid, "cancel")
    assert "grandchild in trouble" in _last("mary")                      # teaches Mary afterwards


def test_vague_then_calm_releases():
    tid = _scam_case()
    case = pipeline.on_customer_reply(tid, "It's for some work at my house.")
    assert case["check"]["followup_question"]
    case = pipeline.on_customer_reply(tid, "Ray is my contractor, I met him in person and checked his license.")
    assert case["transfer"]["status"] == "released"


def test_vague_twice_counts_as_coached():
    tid = _scam_case()
    pipeline.on_customer_reply(tid, "It's for something important.")
    case = pipeline.on_customer_reply(tid, "Please just send it.")
    assert case["transfer"]["status"] == "awaiting_family"


def test_clear_answers_skip_follow_up():
    tid = _scam_case()
    case = pipeline.on_customer_reply(tid, "No one asked me. It's for school fees. Please hurry.")
    assert case["transfer"]["status"] == "awaiting_family" and not case["check"]["followup_question"]
    tid = _scam_case()
    case = pipeline.on_customer_reply(tid, "Ray is my new contractor, I met him and checked his license.")
    assert case["transfer"]["status"] == "released" and not case["check"]["followup_question"]


def test_follow_up_can_be_switched_off():
    config.FOLLOW_UP = False
    try:
        tid = _scam_case()
        case = pipeline.on_customer_reply(tid, "It's for my grandson.")
        assert not case["check"]["followup_question"]
    finally:
        config.FOLLOW_UP = True


def test_playbooks():
    assert playbooks.match("the irs said i owe taxes") == "government"
    assert playbooks.match("the bank told me to move my money to a safe account") == "safe_account"
    assert playbooks.match("rent for my apartment") is None
    q = followup.question("It's for my granddaughter", {"payee_name": "Ray Collins"}, "Mary", "grandparent")
    assert "granddaughter" in q and not any(w in q.lower() for w in followup.FORBIDDEN)
    path = os.path.join(_tmp, "fs"); playbooks.write_files(path)
    assert os.path.exists(os.path.join(path, "playbooks", "grandparent.md"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
