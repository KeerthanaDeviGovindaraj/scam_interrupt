from backend.coaching import detect

coached = [
    "No one asked me. It's for school fees. Please hurry.",
    "It's my own idea, please just send it, it's urgent.",
    "My grandson needs bail tonight, he said not to tell his mom.",
    "The bank told me to move my money to a safe account right away.",
    "I need to buy gift cards for the IRS today.",
]
calm = [
    "It's my monthly gift to my grandson David.",
    "Paying my contractor Ray, I met him and checked his license.",
    "This is for my book club trip next month.",
    "My daughter and I agreed on this yesterday.",
    "Rent for my apartment, same as every month.",
]

correct = 0
for expected, answers in ((True, coached), (False, calm)):
    for a in answers:
        r = detect(a, "Did someone contact you?", {"amount": 3000}, ["new payee"])
        ok = r["coached"] == expected
        correct += ok
        print("OK  " if ok else "MISS", r["detector"], "|", a, "|", r["signals"])
print(f"\n{correct}/10 correct")
