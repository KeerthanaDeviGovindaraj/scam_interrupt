# Keerthana: Agent + Bank

You own: `backend/nessie.py`, `seed.py`, `risk.py`, `coaching.py`, `memory.py`, `pipeline.py`, `agent.py`,
`db.py`, `config.py`, `tests/`. Prize tracks you carry: **Capital One Nessie, LangChain deepagents, Amazon**.
Read `docs/WORK_SPLIT.md` first.

## Fri 8 to 9 PM: set up
- [ ] Create the **public** GitHub repo; push this scaffold to `main` ("Starter scaffold"); add Gayatri
- [ ] `git checkout -b keerthana/agent`
- [ ] Run it offline: `pip install -r requirements.txt`, `cp .env.example .env`, `python -m backend.seed`,
      `uvicorn backend.app:app --reload`, then the Mary demo at http://localhost:8000
- [ ] `python -m tests.test_core` passes
- [ ] Agree on `docs/case_schema.md` with Gayatri

## Fri 9 PM to 1 AM: live Nessie
- [ ] Nessie key from v2.nessieisreal.com → `.env`: `NESSIE_MODE=live`, `NESSIE_KEY=...`
- [ ] `python -m backend.seed` in live mode; fix any field names in `nessie.py` against the Nessie docs
- [ ] Confirm the scam payee (Ray Collins) is its own Nessie customer + account, and merchants include
      gift card and crypto
- [ ] Check `memory.rebuild_habits("mary")` reads her live purchase history (usual amount ~$80–$100)
- [ ] Pick the model now + a backup key; set `MODEL`; install its LangChain package
- [ ] **Sync 1 AM:** Nessie live, model answering

## Sat 7 to 11 AM: agent
- [ ] Coaching Detector with the real model: test 5 coached answers and 5 calm ones; tune the prompt in
      `coaching.py` (rules fallback stays on)
- [ ] `AGENT_MODE=deepagents`: confirm `create_deep_agent` parameter names in the docs; get one clean run
- [ ] `LANGSMITH_TRACING=true`; save a screenshot of one clean trace (backup for the LangChain judges)
- [ ] **Sync 11 AM** (Gayatri is at the career fair 11:00–11:30)

## Sat 12 PM: GATE (full loop live with Gayatri)

## Sat 12 to 10 PM: reliability
- [ ] Decide the demo mode: if deepagents is shaky, demo with `AGENT_MODE=pipeline` and show the trace separately
- [ ] Edge cases: model timeout, Nessie down (switch to mock), double taps, override
- [ ] Add 2–3 tests for anything you fix
- [ ] Run the full demo 10 times with Gayatri
- [ ] **10 PM: feature freeze**

## Talking points you own at judging
- Capital One: "Nessie's accounts, purchases, merchants and transfers drive our risk score; the transfer only
  reaches Nessie after approval."
- LangChain: "A deepagents planner coordinates the sub-agents; here's the trace."
- "Does Nessie really pause transfers?" → "Our app holds it and only posts to Nessie after approval."
