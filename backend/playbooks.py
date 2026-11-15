"""Scam playbooks: name the scam, tell the family what to ask, teach the customer.

Wording (name, family_ask, customer_tip, follow_up) is plain text: Gayatri owns it, edit freely.
Matching logic is Keerthana's. The same playbooks are written as files for the Deep Agents
file system (/playbooks/<key>.md) so the background agent can read them.
"""
import os

PLAYBOOKS = {
    "grandparent": {
        "name": "grandparent emergency scam",
        "summary": "Someone pretends to be a grandchild or relative in trouble (jail, accident, hospital) "
                   "and asks for money fast and in secret.",
        "keywords": ["grandson", "granddaughter", "grandchild", "nephew", "niece", "bail", "jail", "arrested",
                     "accident", "hospital", "lawyer", "attorney", "don't tell", "not to tell", "new number", "lost his phone", "lost her phone", "friend's number", "someone else's phone"],
        "follow_up": "Thanks, {first}. How do you know {payee}, and did you call {relation} back on the number "
                     "you usually use for them?",
        "family_ask": "Ask {first}: “Did you call your grandchild back on their usual number?”",
        "customer_tip": "Scammers often pretend to be a grandchild in trouble and ask you to keep it secret. "
                        "Before sending money, hang up and call them back on the number you already have.",
    },
    "government": {
        "name": "government impersonation scam",
        "summary": "Someone claims to be from the IRS, Social Security, Medicare or the police and demands payment.",
        "keywords": ["irs", "tax", "taxes", "social security", "medicare", "police", "warrant", "fine",
                     "government", "court", "deported"],
        "follow_up": "Thanks, {first}. Which office contacted you, and did you look up their number yourself "
                     "or use the one they gave you?",
        "family_ask": "Ask {first}: “Which agency called you, and did they demand a transfer or gift cards?”",
        "customer_tip": "Government agencies never demand immediate payment by transfer, gift card or crypto. "
                        "Hang up and call the agency on its official number.",
    },
    "safe_account": {
        "name": "\u201csafe account\u201d bank impersonation scam",
        "summary": "A caller pretends to be the bank's fraud team and tells the customer to move money "
                   "to a 'safe' account.",
        "keywords": ["safe account", "fraud department", "fraud team", "bank told me", "protect my money",
                     "account is hacked", "account was hacked", "account hacked", "move my money", "secure account",
                     "keep it safe"],
        "follow_up": "Thanks, {first}. Did someone from a bank tell you to move this money? Real banks never ask "
                     "customers to move money to keep it safe.",
        "family_ask": "Ask {first}: “Did someone saying they’re from the bank tell you to move money?”",
        "customer_tip": "Your bank will never ask you to move money to a \u201csafe account.\u201d If someone does, "
                        "hang up and call the number on the back of your card.",
    },
    "tech_support": {
        "name": "tech support scam",
        "summary": "A pop-up or caller claims the computer is infected and charges for fake repairs or "
                   "'refunds' an overpayment.",
        "keywords": ["computer", "virus", "microsoft", "apple support", "refund", "pop-up", "popup", "remote",
                     "technician", "hacked computer"],
        "follow_up": "Thanks, {first}. Did someone ask to connect to your computer, or say you were owed a refund?",
        "family_ask": "Ask {first}: “Is someone helping you with your computer or a refund right now?”",
        "customer_tip": "Real tech companies don't call you about viruses or refunds. Never let a stranger "
                        "connect to your computer or send money to fix it.",
    },
    "romance": {
        "name": "romance scam",
        "summary": "Someone met online builds a relationship, then needs money for travel, medical bills or "
                   "an emergency, but never meets in person.",
        "keywords": ["boyfriend", "girlfriend", "met online", "dating", "fiance", "fianc\u00e9", "overseas",
                     "soldier", "plane ticket", "customs", "love"],
        "follow_up": "Thanks, {first}. Have you met {payee} in person, and is this for travel or an emergency "
                     "they told you about?",
        "family_ask": "Ask {first}: “Have you met this person in real life?”",
        "customer_tip": "Someone you've only met online who asks for money is very often a scammer, even after "
                        "months of talking.",
    },
    "prize": {
        "name": "prize or lottery scam",
        "summary": "The customer is told they won something but must pay fees or taxes first.",
        "keywords": ["won", "winner", "prize", "lottery", "sweepstakes", "jackpot", "claim fee", "processing fee"],
        "follow_up": "Thanks, {first}. Is this to collect a prize or winnings? Real prizes never ask you to pay first.",
        "family_ask": "Ask {first}: “Were you told you won something?”",
        "customer_tip": "If you have to pay to receive a prize, it isn't a prize. Real winnings never cost you money.",
    },
}

GENERIC = {
    "name": "possible scam",
    "follow_up": "Thanks, {first}. How do you know {payee}, and did anyone ask you to send this quickly or "
                 "keep it private?",
    "family_ask": "Ask {first}: “Who asked you to send this, and did they tell you to keep it secret?”",
    "customer_tip": "If anyone pressures you to send money quickly or secretly, stop and talk to someone you trust first.",
}


WEAK = {"grandson", "granddaughter", "grandchild", "nephew", "niece"}   # family words alone aren't a scam sign


def scores(text: str) -> dict:
    t = (text or "").lower()
    return {key: sum(0.5 if k in WEAK else 1 for k in pb["keywords"] if k in t) for key, pb in PLAYBOOKS.items()}


def strength(text: str) -> float:
    """How strongly the text matches any scam playbook (family words count half)."""
    return max(scores(text).values() or [0])


def match(text: str, reasons=None) -> str | None:
    """Best-matching playbook key for what the customer said, or None."""
    sc = scores(text)
    best = max(sc, key=sc.get) if sc else None
    return best if best and sc[best] > 0 else None


def get(key: str | None) -> dict:
    return PLAYBOOKS.get(key or "", GENERIC)


def name(key: str | None) -> str:
    return get(key)["name"]


def write_files(root: str) -> None:
    """Write each playbook as /playbooks/<key>.md for the Deep Agents file system."""
    os.makedirs(os.path.join(root, "playbooks"), exist_ok=True)
    for key, pb in PLAYBOOKS.items():
        with open(os.path.join(root, "playbooks", f"{key}.md"), "w") as f:
            f.write(f"# {pb['name'].capitalize()}\n\n{pb['summary']}\n\n"
                    f"## Warning words\n{', '.join(pb['keywords'])}\n\n"
                    f"## What to ask the family\n{pb['family_ask']}\n\n"
                    f"## What to teach the customer\n{pb['customer_tip']}\n")
