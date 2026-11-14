"""Risk Scorer sub-agent: transparent rules, so the demo is predictable and
every hold comes with reasons a person can understand."""
from . import config

RISKY_CATEGORIES = {"gift_card": "gift card purchase", "crypto": "crypto purchase"}


def score(amount: float, payee_id: str, category: str, hour: int, habits: dict, context: dict | None = None) -> dict:
    """context (optional, from Nessie + our records):
       available: spendable balance in dollars; bills: [{"payee", "amount", "due"}]; watchlist_hits: int"""
    points, reasons = 0, []
    ctx = context or {}
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

    # --- Capital One Nessie context ---
    hits = int(ctx.get("watchlist_hits") or 0)
    if hits:
        points += 40
        reasons.append(f"payee linked to {hits} stopped scam{'s' if hits > 1 else ''}")
    available = ctx.get("available")
    if available is not None:
        available = float(available)
        if amount > available:
            points += 20
            reasons.append(f"more than the available balance (${available:,.0f})")
        else:
            left = available - amount
            bills = sorted(ctx.get("bills") or [], key=lambda b: str(b.get("due") or ""))
            short = next((b for b in bills if float(b.get("amount") or 0) > left), None)
            if short:
                points += 15
                due = f" due {short['due']}" if short.get("due") else ""
                reasons.append(f"would leave ${left:,.0f}, not enough for {short['payee']} (${float(short['amount']):,.0f}{due})")
            elif available > 0 and amount >= 0.8 * available:
                points += 10
                reasons.append(f"uses {round(100 * amount / available)}% of the available balance")

    level = "high" if points >= config.RISK_HIGH else ("medium" if points >= 30 else "low")
    return {"score": min(points, 100), "level": level, "reasons": reasons}
