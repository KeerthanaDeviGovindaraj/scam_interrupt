"""Measure the safety check: scams caught, false alarms, follow-up rate. Writes docs/eval_results.md.

    python -m scripts.eval_coaching          # uses MODEL from .env (falls back to rules if unavailable)
    MODEL= python -m scripts.eval_coaching   # rules only, no API calls

Labels: "scam" or "ok". Vague first answers come with the second answer the person gives after the follow-up.
Report numbers honestly in the pitch: this is our own 30-case test set, not real-world data.
"""
import os
import time
from collections import Counter

from backend import config, followup

T = {"amount": 3000, "payee_name": "Ray Collins", "hour": 23,
     "reasons": ["new payee", "about 24x the usual amount", "unusual time (23:00)",
                 "would leave $500, not enough for Rent ($1,200)"]}
Q = "Did someone contact you and ask you to send this? Did they say it was urgent or secret?"

CASES = [  # (label, first answer, second answer if a follow-up is asked)
    ("scam", "No one asked me. It's for school fees. Please hurry.", None),
    ("scam", "It's my own idea, please just send it, it's urgent.", None),
    ("scam", "My grandson needs bail tonight, he said not to tell his mom.", None),
    ("scam", "The bank told me to move my money to a safe account right away.", None),
    ("scam", "I need to buy gift cards for the IRS today.", None),
    ("scam", "I won a prize and have to pay the processing fee first.", None),
    ("scam", "Microsoft said my computer has a virus and I owe them for the repair.", None),
    ("scam", "My boyfriend I met online needs money for a plane ticket to see me.", None),
    ("scam", "Social Security said there's a warrant and I must pay the fine now.", None),
    ("scam", "Don't worry about it, nobody contacted me. Just send it quickly please.", None),
    ("ok", "Ray is my new contractor, I met him and checked his license.", None),
    ("ok", "It's my monthly gift to my grandson David.", None),
    ("ok", "Rent for my apartment, same as every month.", None),
    ("ok", "My daughter and I agreed on this yesterday, it's for her car repair.", None),
    ("ok", "Ray is my neighbor, he fixed my roof and gave me an invoice.", None),
    ("ok", "This is for my book club trip next month, Ray is our treasurer at church.", None),
    ("ok", "Ray Collins is my nephew's landlord, I'm helping with his deposit as we discussed at dinner.", None),
    ("ok", "Paying Ray back for the furniture he bought for me, I've known him for years.", None),
    ("ok", "My son set this up with me last week for his tuition, Ray is the school's agent we met.",
     "We paid the school through Ray last semester too, my son and I have the receipt."),
    ("ok", "It's the deposit for my new apartment, I toured it with Ray the landlord on Monday.", None),
    ("scam", "It's for my grandson.", "He called from a new number and said not to tell his mom. Ray is his lawyer."),
    ("scam", "It's for something important.", "Please just send it, I don't have time for this."),
    ("scam", "A man from my bank needs it.", "He said my account was hacked and I must move my money to keep it safe."),
    ("scam", "It's for a friend.", "We met online, he is overseas and needs money for customs."),
    ("scam", "It's a fee.", "I won the lottery and they need the fee before they pay me."),
    ("ok", "It's for some work at my house.", "Ray is my contractor, I met him in person and checked his license."),
    ("ok", "It's for my granddaughter.", "I called her back on her usual number, Ray is her landlord, it's her rent."),
    ("ok", "It's a payment I owe.", "Ray is my plumber, he fixed the pipes last week and sent an invoice."),
    ("ok", "It's for the trip.", "Ray is my brother-in-law, he booked our family trip and I'm paying my share."),
    ("ok", "It's for my church.", "Ray is our church treasurer, I've known him for years, it's my pledge."),
]


def run():
    rows, tally, detectors = [], Counter(), Counter()
    for label, first, second in CASES:
        r = followup.classify(first, T, Q)
        detectors[r["detector"]] += 1
        asked = r["verdict"] == "unclear"
        if asked:
            q = followup.question(first, T, "Mary", r["scam_type"])
            r = followup.classify(second or "I don't know.", T, Q, first_answer=first, follow_up_question=q)
            detectors[r["detector"]] += 1
        flagged = r["verdict"] == "coached"
        tally[(label, flagged)] += 1
        tally[("asked", label)] += asked
        rows.append((label, first, "yes" if asked else "", "family alerted" if flagged else "sent", r["detector"]))
        if config.MODEL:
            time.sleep(0.6)  # stay under free-tier rate limits
    scams = sum(1 for c in CASES if c[0] == "scam"); oks = len(CASES) - scams
    caught, false_alarms = tally[("scam", True)], tally[("ok", True)]
    correct = caught + (oks - false_alarms)
    summary = {
        "cases": len(CASES), "accuracy": f"{correct}/{len(CASES)} ({100 * correct // len(CASES)}%)",
        "scams caught": f"{caught}/{scams}", "false alarms": f"{false_alarms}/{oks}",
        "follow-up asked (scam / ok)": f"{tally[('asked', 'scam')]} / {tally[('asked', 'ok')]}",
        "detector calls": dict(detectors),
    }
    return summary, rows


def write_md(summary, rows):
    lines = ["# Safety-check evaluation", "",
             f"Model: `{config.MODEL or 'rules only'}` · follow-up: {'on' if config.FOLLOW_UP else 'off'}", "",
             "Our own 30-case test set (20 clear answers, 10 vague answers with a second reply). "
             "Not real-world data.", "", "| Metric | Result |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in summary.items()]
    lines += ["", "| Label | First answer | Follow-up asked | Outcome | Detector |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    os.makedirs("docs", exist_ok=True)
    open("docs/eval_results.md", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    s, r = run()
    for k, v in s.items():
        print(f"{k:28} {v}")
    write_md(s, r)
    print("\nWrote docs/eval_results.md")
