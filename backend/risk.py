"""Risk Scorer sub-agent: transparent rules, so the demo is predictable and
every hold comes with reasons a person can understand."""
from . import config

RISKY_CATEGORIES = {"gift_card": "gift card purchase", "crypto": "crypto purchase"}


def score(amount: float, payee_id: str, category: str, hour: int, habits: dict) -> dict:
    points, reasons = 0, []
    usual_payees = set(habits.get("usual_payees") or [])
    avg = float(habits.get("avg_amount") or 0)
    mx = float(habits.get("max_amount") or 0)

    if payee_id not in usual_payees:
        points += 30
        reasons.append("new payee")
    if avg > 0:
        ratio = amount / avg
        if ratio >= 5:
            points += 30
            reasons.append(f"about {round(ratio)}x the usual amount")
        elif mx and amount > 1.5 * mx:
            points += 15
            reasons.append("larger than any recent payment")
    if category in RISKY_CATEGORIES:
        points += 30
        reasons.append(RISKY_CATEGORIES[category])
    if hour < 7 or hour >= 22:
        points += 10
        reasons.append(f"unusual time ({hour}:00)")

    level = "high" if points >= config.RISK_HIGH else ("medium" if points >= 30 else "low")
    return {"score": min(points, 100), "level": level, "reasons": reasons}
