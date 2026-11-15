# Safety-check evaluation

Model: `groq:openai/gpt-oss-120b` · follow-up: on

Held-out set: 10 answers (5 scam, 5 honest) written independently of the rules. Not real-world data.

| Metric | Result |
| --- | --- |
| cases | 10 |
| accuracy | 7/10 (70%) |
| scams caught | 5/5 |
| false alarms | 3/5 |
| follow-up asked (scam / ok) | 1 / 1 |
| detector calls | {'llm': 12} |

| Label | First answer | Follow-up asked | Outcome | Detector |
| --- | --- | --- | --- | --- |
| scam | He said you would ask this. Everything is fine, please process it. |  | family alerted | llm |
| scam | My nephew needs it for a car repair, he lost his phone so he's using a friend's number. |  | family alerted | llm |
| scam | It's fine, the person is waiting on the line with me right now. |  | family alerted | llm |
| scam | Yes it's for a lawyer. I was asked not to discuss the case with anyone. |  | family alerted | llm |
| scam | It's for family. | yes | family alerted | llm |
| ok | I'm buying a piano from Ray, I saw it in person yesterday and my son came with me. |  | sent | llm |
| ok | It's for my dentist, the crown wasn't covered by insurance. I just got the bill today. |  | family alerted | llm |
| ok | No one contacted me. It's for my lawyer who is handling my will, I've used her for years. |  | family alerted | llm |
| ok | Nobody, I'm paying the moving company. They come tomorrow so I wanted it done today. |  | family alerted | llm |
| ok | It's a payment. | yes | sent | llm |
