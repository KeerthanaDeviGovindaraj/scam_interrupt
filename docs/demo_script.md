# 2-minute demo (rehearse 10 times with seeded data)

Setup: run `POST /api/demo/reset` (button on the home page). Laptop shows the dashboard.
Phone 1 (OUR phone, handed to the judge) = Mary. Phone 2 (held by a teammate) = David.
If Photon is not live, use /web/phones.html on a second screen.

| Time | What happens | What we say |
|---|---|---|
| 0:00-0:15 | Hook | Verified FTC stat on fraud against older adults (check ftc.gov). "Scammers coach victims on exactly what to tell the bank." |
| 0:15-1:15 | Judge plays Mary: sends $3,000 to Ray Collins at 11 PM. Safety check arrives. Judge reads the scammer's script: "No one asked me. It's for school fees. Please hurry." | "Normal payments go straight through. This one is a new payee, 15x her usual amount, at 11 PM, so we pause it and ask." |
| 1:15-1:35 | David's phone gets the alert; teammate taps Cancel | "Nothing reached the bank. Nessie only sees the transfer if it's approved." |
| 1:35-1:50 | Dashboard: "$3,000 protected" | Name each sponsor tool as it appears; show the LangSmith trace if asked. |
| 1:50-2:00 | Close | "Most tools tell you after the money is gone. Scam Interrupt asks before it leaves." |

Backups: a recorded 2-minute video; offline mode (NESSIE_MODE=mock, PHOTON_MODE=sim) still runs the whole loop.
