"""Measure the safety check: scams caught, false alarms, follow-up rate. Writes docs/eval_heldout_results.md.

    python -m scripts.eval_coaching          # uses MODEL from .env (falls back to rules if unavailable)
    MODEL= python -m scripts.eval_coaching   # rules only, no API calls

Labels: "scam" or "ok". Vague first answers come with the second answer the person gives after the follow-up.
Report numbers honestly in the pitch: this is a 10-case held-out set written independently of the rules, not real-world data.
"""
import os
import time
from collections import Counter

from backend import config, followup

T = {"amount": 3000, "payee_name": "Ray Collins", "hour": 23,
     "reasons": ["new payee", "about 24x the usual amount", "unusual time (23:00)",
                 "would leave $500, not enough for Rent ($1,200)"]}
Q = "Did someone contact you and ask you to send this? Did they say it was urgent or secret?"

CASES = [  # HELD-OUT: written independently of the rules; report these separately
    ("scam", "He said you would ask this. Everything is fine, please process it.", None),
    ("scam", "My nephew needs it for a car repair, he lost his phone so he's using a friend's number.", None),
    ("scam", "It's fine, the person is waiting on the line with me right now.", None),
    ("scam", "Yes it's for a lawyer. I was asked not to discuss the case with anyone.", None),
    ("scam", "It's for family.", "My grandson's friend called, he's been arrested and asked me not to tell anyone."),
    ("ok", "I'm buying a piano from Ray, I saw it in person yesterday and my son came with me.", None),
    ("ok", "It's for my dentist, the crown wasn't covered by insurance. I just got the bill today.", None),
    ("ok", "No one contacted me. It's for my lawyer who is handling my will, I've used her for years.", None),
    ("ok", "Nobody, I'm paying the moving company. They come tomorrow so I wanted it done today.", None),
    ("ok", "It's a payment.", "Ray is my financial advisor at my credit union, I met him at the branch."),
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
    open("docs/eval_heldout_results.md", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    s, r = run()
    for k, v in s.items():
        print(f"{k:28} {v}")
    write_md(s, r)
    print("\nWrote docs/eval_heldout_results.md")
