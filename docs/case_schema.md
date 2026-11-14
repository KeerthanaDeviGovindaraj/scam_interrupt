# Shared case object

Agree on this on hour one so Person A (agent + bank) and Person B (Photon + demo) can build separately.
`GET /api/cases/{transfer_id}` returns it; the deepagents planner receives it with every event.

```json
{
  "transfer": {
    "id": 7, "customer_id": "mary", "payee_id": "<nessie account or merchant id>",
    "payee_name": "Ray Collins", "payee_kind": "account", "category": "transfer",
    "amount": 3000, "hour": 23,
    "status": "awaiting_customer | awaiting_family | held_review | released | cancelled",
    "risk_score": 70, "risk_level": "high",
    "reasons": ["new payee", "about 15x the usual amount", "unusual time (23:00)"],
    "nessie_ref": null, "note": ""
  },
  "customer": {"id": "mary", "name": "Mary Lee", "trusted_contact_id": "david", "family_opt_in": 1},
  "check": {"question": "...", "transcript": "...", "signals": ["urgency or pressure"], "coached": 1,
            "explanation": "...", "detector": "llm | rules"},
  "alert": {"contact_id": "david", "message": "...", "decision": "approve | cancel | null"}
}
```

## Events
| Event | Sent by | What happens next |
|---|---|---|
| `transfer_scored` | app, after Risk Scorer | high risk -> safety check; else release to Nessie |
| `customer_replied` | Photon webhook or phone simulator | Coaching Detector -> family alert or release |
| `family_decided` | Photon webhook or simulator | approve -> release; cancel -> nothing reaches Nessie |
| `customer_override` | bank app "Send anyway" | release (customer keeps the final say) |
