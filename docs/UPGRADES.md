# Upgrades: follow-up question, scam playbooks, evaluation, Nessie decision hooks

Tag the working version first, so you can always go back:
```bash
git tag demo-safe && git push origin demo-safe
```

## 1. Install (Keerthana, on your branch, 10 minutes)
```bash
unzip -o ~/Downloads/upgrades.zip -d .
python apply_upgrades.py          # every line should say "changed" (or "already done"); paste any NOT FOUND
python -m tests.test_core && python -m tests.test_followup && python -m tests.test_hooks && python -m tests.test_agent
```
Add to `.env`:
```
FOLLOW_UP=true
NESSIE_HOLD=app
```
Restart the server, then commit, push and merge to `main`. Gayatri pulls `main` on the demo laptop.

## 2. Adaptive follow-up + scam playbooks
**What it does:** if Mary's first answer is vague, she gets ONE follow-up question built from her own words.
Clear scam answers go straight to the family; clear, ordinary answers go straight through. After the follow-up,
anything still unclear goes to the family. The family alert now names the scam and says what to ask, and after a
cancel Mary gets a short, kind explanation of the scam.

**Try it (both, 10 minutes):**
1. $3,000 to Ray at 11 PM.
2. Mary replies: `It's for my grandson.` → she gets a follow-up asking how she knows Ray and whether she
   called her grandson back on his usual number.
3. Mary replies: `He called from a new number and said not to tell his mom. Ray is his lawyer.`
4. David's alert starts with "This looks like a grandparent emergency scam" and says what to ask.
5. David cancels → Mary gets the explanation. The dashboard row shows "Looks like: grandparent emergency scam."

**Who owns what**
- **Keerthana:** `backend/followup.py` (logic), `backend/playbooks.py` keywords and matching.
- **Gayatri:** the wording in `backend/playbooks.py` (`name`, `follow_up`, `family_ask`, `customer_tip`):
  read every message on a real phone and make it warm and short. Keep `{first}`, `{payee}`, `{relation}`.
  Also check the follow-up arrives through Photon and Mary's second reply comes back.

Turn it off any time: `FOLLOW_UP=false`.

## 3. Real accuracy numbers (both, 20 minutes)
```bash
python -m scripts.eval_coaching      # uses your MODEL; writes docs/eval_results.md
```
**Be honest about the numbers.** The rules were tuned on these same 30 cases, so their score is optimistic.
For a fair number:
1. Gayatri writes **10 new answers** (5 scam, 5 ordinary, a few vague with a second reply) **without looking
   at the rules**, and adds them to `CASES` in `scripts/eval_coaching.py`.
2. Run the eval again and report the result on those new cases, and say in the pitch: "On our own test set of
   40 answers, we caught X of Y scams with Z false alarms."

## 4. Nessie decision hooks (only if 1–3 are merged by 4–5 pm)
**What it does:** the transfer is created in Nessie right away (pending, money held by the bank). Nessie asks our
server before settling: we approve normal payments at once, ask Nessie to wait while Mary and David answer, then
approve or decline. If our server is unreachable, Nessie declines (fail safe).

**Gayatri (demo laptop, needs the public ngrok URL):**
```bash
ngrok http 8000                                              # if not already running for Photon
python -m scripts.register_nessie_hook https://<your-id>.ngrok-free.app
```
Copy the printed `NESSIE_HOOK_SECRET=...` into `.env`, set `NESSIE_HOLD=hook` and `PUBLIC_URL=https://<your-id>.ngrok-free.app`,
restart the server. Re-run the register command whenever the ngrok URL changes.

**Test (both):**
1. $120 to David at 2 PM → sent within seconds; the server log shows `POST /webhooks/nessie-decision` → 200.
2. $3,000 to Ray at 11 PM → held; the log shows 202 answers every ~25 seconds.
3. Mary's reply, then David cancels within 5 minutes → in Nessie, the transaction shows **declined** with
   our reason:
   ```bash
   curl -s -H "Authorization: Bearer $(grep NESSIE_KEY .env | cut -d= -f2)" \
     "https://v2-prod-api.nessieisreal.com/transactions?limit=3" | python -m json.tool | head -40
   ```
4. If anything goes wrong: `NESSIE_HOLD=app`, restart. You're back to the working design.

**Limits to know:** Nessie waits at most 5 minutes; after that it declines. If David approves later, we send a fresh
transfer automatically. Hooks need the public URL, so they only work on the laptop running ngrok.

## Pitch lines
- Follow-up: "We don't ask scripted questions. We ask the one question a scammer didn't prepare her for."
- Playbooks: "David doesn't just get an alarm. He's told it looks like a grandparent scam and exactly what to ask."
- Hooks (Capital One): "The bank itself waits for our answer. Here's the declined transaction in Nessie, with our reason."
