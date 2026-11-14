# Safety-check evaluation

Model: `groq:openai/gpt-oss-120b` · follow-up: on

Our own 30-case test set (20 clear answers, 10 vague answers with a second reply). Not real-world data.

| Metric | Result |
| --- | --- |
| cases | 30 |
| accuracy | 29/30 (96%) |
| scams caught | 15/15 |
| false alarms | 1/15 |
| follow-up asked (scam / ok) | 5 / 7 |
| detector calls | {'llm': 13, 'rules': 29} |

| Label | First answer | Follow-up asked | Outcome | Detector |
| --- | --- | --- | --- | --- |
| scam | No one asked me. It's for school fees. Please hurry. |  | family alerted | llm |
| scam | It's my own idea, please just send it, it's urgent. |  | family alerted | llm |
| scam | My grandson needs bail tonight, he said not to tell his mom. |  | family alerted | llm |
| scam | The bank told me to move my money to a safe account right away. |  | family alerted | llm |
| scam | I need to buy gift cards for the IRS today. |  | family alerted | llm |
| scam | I won a prize and have to pay the processing fee first. |  | family alerted | llm |
| scam | Microsoft said my computer has a virus and I owe them for the repair. |  | family alerted | llm |
| scam | My boyfriend I met online needs money for a plane ticket to see me. |  | family alerted | llm |
| scam | Social Security said there's a warrant and I must pay the fine now. |  | family alerted | llm |
| scam | Don't worry about it, nobody contacted me. Just send it quickly please. |  | family alerted | llm |
| ok | Ray is my new contractor, I met him and checked his license. |  | sent | llm |
| ok | It's my monthly gift to my grandson David. | yes | family alerted | llm |
| ok | Rent for my apartment, same as every month. |  | sent | rules |
| ok | My daughter and I agreed on this yesterday, it's for her car repair. |  | sent | rules |
| ok | Ray is my neighbor, he fixed my roof and gave me an invoice. |  | sent | rules |
| ok | This is for my book club trip next month, Ray is our treasurer at church. |  | sent | rules |
| ok | Ray Collins is my nephew's landlord, I'm helping with his deposit as we discussed at dinner. |  | sent | rules |
| ok | Paying Ray back for the furniture he bought for me, I've known him for years. |  | sent | rules |
| ok | My son set this up with me last week for his tuition, Ray is the school's agent we met. | yes | sent | rules |
| ok | It's the deposit for my new apartment, I toured it with Ray the landlord on Monday. |  | sent | rules |
| scam | It's for my grandson. | yes | family alerted | rules |
| scam | It's for something important. | yes | family alerted | rules |
| scam | A man from my bank needs it. | yes | family alerted | rules |
| scam | It's for a friend. | yes | family alerted | rules |
| scam | It's a fee. | yes | family alerted | rules |
| ok | It's for some work at my house. | yes | sent | rules |
| ok | It's for my granddaughter. | yes | sent | rules |
| ok | It's a payment I owe. | yes | sent | rules |
| ok | It's for the trip. | yes | sent | rules |
| ok | It's for my church. | yes | sent | rules |
