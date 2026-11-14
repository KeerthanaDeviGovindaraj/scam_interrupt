# Work split: Keerthana and Gayatri

**Rule:** each person edits only the files they own. Anything in the shared contract
(`docs/case_schema.md`, API routes in `app.py`) is changed only after a 2-minute chat.

| | Keerthana: Agent + Bank | Gayatri: Photon + Demo |
|---|---|---|
| Owns | `nessie.py`, `seed.py`, `risk.py`, `coaching.py`, `memory.py`, `pipeline.py`, `agent.py`, `db.py`, `config.py`, `tests/` | `photon_adapter.py`, `messaging.py`, `app.py`, `web/`, `docs/demo_script.md`, `README.md` |
| Prize tracks carried | Capital One (Nessie), LangChain (deepagents), Amazon | Photon Messaging, Photon Best Voice |
| Non-code | LangSmith trace screenshot, answer technical judge questions | Career fair (30 min, Sat 11 AM), Devpost, video, pitch, sponsor tables, Peri (optional) |

## Git workflow
1. **After 8 PM Friday:** Keerthana creates the public GitHub repo and pushes the scaffold to `main`
   (first commit message: "Starter scaffold").
2. Gayatri clones it (don't push a second copy).
3. Each works on a branch: `keerthana/agent` and `gayatri/photon`.
4. Merge to `main` at every sync point via a pull request; the other person skims it.
5. `git pull origin main` right after each sync.

## Sync points (10 minutes each)
| When | Check |
|---|---|
| Fri 9 PM | Both run the app offline; case JSON agreed |
| Sat 1 AM | Nessie live seeded; Photon sends + receives one message |
| Sat 11 AM | Coaching Detector + planner working; Photon safety check working |
| **Sat 12 PM** | **GATE: full loop live** (bank app → Photon check → family Cancel → dashboard). If not, cut voice |
| Sat 6 PM | Demo run 5 times; video plan |
| Sat 10 PM | Feature freeze |
| Sun 2 AM | Final run; submit by 3 AM |

## Handoffs (who needs what from whom)
- Keerthana → Gayatri: `pipeline.on_customer_reply()` and `on_family_decision()` work (already do offline).
- Gayatri → Keerthana: real phone replies arrive at `POST /webhooks/photon` and call those functions.
- Both: the demo uses Gayatri's phone as "Mary" (handed to the judge) and Keerthana's phone as "David".
