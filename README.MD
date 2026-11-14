# Scam Interrupt

> **Most tools tell you after the money is gone. Scam Interrupt asks before it leaves.**

Scam Interrupt is an AI agent that pauses risky bank transfers, checks in with the customer through a short
safety conversation, catches signs that a scammer is coaching them, and brings an opted-in trusted family
member in **before** the money moves. Normal payments go straight through, and the customer always keeps
the final say.

Built at **HackPrinceton Fall 2026** · Main track: **Business and Enterprise**

| Sponsor tool | How we use it |
|---|---|
| **Capital One Nessie** | Accounts, purchases, merchants and transfers drive the risk score; a held transfer is posted to Nessie only after approval |
| **Photon 2.0** | The customer safety check and the family Approve/Cancel alert |
| **LangChain deepagents** | A planner that decides the next step and coordinates the sub-agents |
| **AI model (e.g. Amazon Bedrock)** | Coaching Detector that returns structured JSON, with a rule-based fallback |

> **Starter scaffold note:** this repository began from an AI-generated starter scaffold. All project work
> happened during HackPrinceton (Nov 13–15, 2026); see the commit history.

---

## The problem

Scammers create panic ("your grandson is in jail," "your account is hacked"), then coach their victims, often
older adults, on exactly what to tell the bank. Bank fraud checks ask yes/no questions the victim has already
been told how to answer, and most protection tools alert family only **after** the money is gone.

## What it does: Grandma Mary's story

1. A scammer texts Mary pretending to be her grandson, needing $3,000 for bail, and tells her to keep it secret.
2. Mary sends $3,000 in her bank app. **Scam Interrupt holds it; nothing is sent to Nessie yet.**
3. **Risk Scorer:** new payee, about 15x her usual amount, 11 PM → high risk, with reasons.
4. **Safety check:** "Did someone contact you and ask you to send this? Did they say it was urgent or secret?"
   Coached, Mary replies: "No one asked me. It's for school fees. Please hurry."
5. **Coaching Detector:** urgency, denial of contact, and a story that doesn't fit a new payee → hold.
6. **Family alert:** David, Mary's opted-in trusted contact, gets **Approve** / **Cancel**.
7. David calls Mary and taps **Cancel**. The transfer never reaches the bank.
8. **Memory** updates Mary's habits; the dashboard shows **"$3,000 protected."**
9. Mary can still tap **Send anyway**: the customer keeps the final say.

---

## Quick start (offline, about 2 minutes)

Works with no API keys: mock Nessie, an on-screen phone simulator, and rule-based coaching detection.

```bash
git clone <your-repo-url> scam-interrupt && cd scam-interrupt
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # defaults: NESSIE_MODE=mock, PHOTON_MODE=sim, rules
python -m backend.seed               # Mary, David, the scam payee, merchants, 30 days of history
uvicorn backend.app:app --reload --port 8000
```

Open **http://localhost:8000**, then:

1. **Mary's bank app:** send $3,000 to *Ray Collins* at *11 PM*.
2. **Phones:** in Mary's phone, reply `No one asked me. It's for school fees. Please hurry.`
3. **Phones:** in David's phone, tap **Cancel**.
4. **Bank dashboard:** "$3,000 protected · 1 scam stopped."

Reset the demo any time with the **Reset and seed demo data** button on the home page.

**Run the tests:**
```bash
python -m tests.test_core            # or: pip install pytest && python -m pytest -q
```

---

## Going live

Do these in order; the app keeps working offline at every step.

### 1. Capital One Nessie
1. Get an API key at **v2.nessieisreal.com**.
2. In `.env`: `NESSIE_MODE=live` and `NESSIE_KEY=<your key>`.
3. Re-seed: `python -m backend.seed`.
4. On the first live run, check the request fields in `backend/nessie.py` against the Nessie docs.

### 2. Photon 2.0 (required for the Photon prizes)
1. Sign up at **photon.codes/beta** and read Photon's hackathon guidelines page.
2. Implement `send_text()` and `send_choices()` in **`backend/photon_adapter.py`**.
3. In `.env`: `PHOTON_MODE=live`, `PHOTON_API_KEY=<key>`, and the teammates' real numbers in
   `MARY_PHONE` / `DAVID_PHONE` (with their consent).
4. If Photon delivers replies by webhook, expose **`POST /webhooks/photon`** on a public URL (deploy the app,
   or run a tunnel such as `ngrok http 8000`) and map Photon's payload fields in `backend/app.py`.
5. Voice: if Photon supports calls, add a voice safety check; otherwise the text safety check is used.

> A substitute such as Twilio makes the project ineligible for the Photon tracks.

### 3. AI model
Set `MODEL` in `.env` and install its LangChain provider package, for example:

| MODEL value | Package |
|---|---|
| `anthropic:claude-sonnet-4-5` | `langchain-anthropic` |
| `bedrock_converse:<model-id>` | `langchain-aws` |
| `openai:gpt-4o-mini` | `langchain-openai` |

If the model is unavailable or returns bad JSON, the Coaching Detector falls back to rules automatically.

### 4. deepagents planner
Set `AGENT_MODE=deepagents` (needs `MODEL`). The planner receives each event plus the case JSON and chooses
the next tool. If the agent errors, the app falls back to the fixed pipeline. Confirm the
`create_deep_agent` parameter names against the current deepagents docs.

To show judges the agent trace, set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`.

---

## Architecture

```
 Mary's bank app ──► API (FastAPI) ──► Risk Scorer ──► low risk ──► Nessie transfer ✓
                                           │
                                       high risk (held)
                                           ▼
                        Safety Interviewer (Photon) ──► Mary's answer
                                           ▼
                               Coaching Detector (LLM / rules)
                                 │                      │
                             not coached             coached
                                 ▼                      ▼
                          Nessie transfer ✓    Family Notifier (Photon)
                                                  │            │
                                               Approve       Cancel
                                                  ▼            ▼
                                          Nessie transfer ✓   nothing sent
                                           ▼
                                    Memory (habits) + Dashboard
```

| Sub-agent | Input | Output | File |
|---|---|---|---|
| Risk Scorer | Transfer, payee, habits | Risk level + reasons | `backend/risk.py` |
| Safety Interviewer | Risk reasons | Question + transcript | `backend/pipeline.py`, `backend/photon_adapter.py` |
| Coaching Detector | Customer's answer | Signals + coached yes/no | `backend/coaching.py` |
| Family Notifier | Decision, transfer | Approve or Cancel | `backend/pipeline.py` |
| Memory | Every outcome | Usual payees, amounts, hours | `backend/memory.py` |

**Two run modes:**
- `AGENT_MODE=pipeline`: the steps run in a fixed order. Safest for live demos.
- `AGENT_MODE=deepagents`: a LangChain deepagents planner decides the next step (`backend/agent.py`).

**Data (SQLite):** `customers`, `merchants`, `transfers`, `checks`, `alerts`, `habits`, `messages`.
The shared case object is documented in [`docs/case_schema.md`](docs/case_schema.md).

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Modes in use (Nessie, Photon, agent, model) |
| POST | `/api/demo/reset` | Wipe and re-seed demo data |
| GET | `/api/payees?customer_id=mary` | People and merchants Mary can pay |
| POST | `/api/transfers` | Request a transfer `{customer_id, payee_id, amount, hour?}` |
| GET | `/api/transfers` | All transfers |
| GET | `/api/cases/{id}` | Full case: transfer, customer, check, alert |
| POST | `/api/cases/{id}/reply` | Customer's safety-check answer `{text}` |
| POST | `/api/cases/{id}/family` | Trusted contact's decision `{decision: approve\|cancel}` |
| POST | `/api/cases/{id}/override` | Customer's "Send anyway" |
| GET | `/api/phone/{owner_id}` | Messages for the phone simulator |
| GET | `/api/dashboard` | Money protected, scams stopped, false-alarm rate |
| POST | `/webhooks/photon` | Inbound Photon messages (map payload fields) |

Interactive API docs: **http://localhost:8000/docs**

---

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `NESSIE_MODE` | `mock` | `mock` (offline) or `live` |
| `NESSIE_KEY` | | Nessie API key |
| `PHOTON_MODE` | `sim` | `sim` (on-screen phones) or `live` (also sends via Photon) |
| `PHOTON_API_KEY` | | Photon 2.0 key |
| `MODEL` | | LangChain model id; empty = rule-based detector |
| `AGENT_MODE` | `pipeline` | `pipeline` or `deepagents` |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` | `false` | Show the agent trace |
| `MARY_PHONE` / `DAVID_PHONE` | test numbers | Demo phones (teammates, with consent) |
| `DB_PATH` | `data/scam_interrupt.db` | SQLite file |

---

## Project layout

```
scam-interrupt/
├── backend/
│   ├── app.py              FastAPI: API, static pages, Photon webhook
│   ├── pipeline.py         case flow as small tools (also used by the agent)
│   ├── agent.py            deepagents planner + coaching-detector sub-agent
│   ├── risk.py             Risk Scorer rules
│   ├── coaching.py         Coaching Detector (LLM JSON + rules fallback)
│   ├── memory.py           habits from Nessie history
│   ├── nessie.py           Capital One Nessie client (live + offline mock)
│   ├── messaging.py        message log; sends via Photon in live mode
│   ├── photon_adapter.py   ← finish with Photon's docs
│   ├── seed.py             demo data
│   ├── db.py, config.py
├── web/                    index, bank, phones, dashboard pages
├── docs/                   case schema, demo script, playbook PDF
├── tests/test_core.py      end-to-end demo flow (offline)
├── requirements.txt
└── .env.example
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Unknown payee` or empty payee list | Run `python -m backend.seed` (or the reset button) |
| `StaticFiles` directory error | Start uvicorn from the repo root, not from `backend/` |
| Nessie 4xx errors | Check `NESSIE_KEY`, then compare field names in `backend/nessie.py` with the docs |
| Photon replies never arrive | Your webhook URL must be public (deploy or tunnel) and the payload fields mapped in `app.py` |
| Model errors | The detector falls back to rules; check `MODEL` and the provider package |
| Agent does nothing | Leave `AGENT_MODE=pipeline` for the demo; check the LangSmith trace |

---

## Privacy and safety

- Mock bank data only; no real customer data.
- Demo phones belong to teammates, used with their consent.
- Family alerts require the customer's prior opt-in.
- The customer can always send a held payment anyway; Scam Interrupt adds a pause and a second voice, nothing more.

## What's next

A pilot with a local credit union, live voice safety calls, and false-alarm tracking over time.

## Team

- **Keerthana Devi Govindaraj** ([@KeerthanaDeviGovindaraj](https://github.com/KeerthanaDeviGovindaraj)): agent and bank (Nessie, Risk Scorer, Coaching Detector, deepagents planner)
- **Gayatri Sawant**: Photon and demo (safety check, family alert, bank app, dashboard, pitch)

See [`docs/WORK_SPLIT.md`](docs/WORK_SPLIT.md) for who owns which files.
