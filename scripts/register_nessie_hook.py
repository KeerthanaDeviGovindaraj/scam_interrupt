"""Register the Nessie decision hook (run once on the DEMO laptop, after ngrok is running).

    python -m scripts.register_nessie_hook https://<your-ngrok-id>.ngrok-free.app

Prints the signing secret: put it in .env as NESSIE_HOOK_SECRET=... and set NESSIE_HOLD=hook,
then restart the server. Re-run whenever the ngrok URL changes (it replaces the old hook).
"""
import sys

from backend import config
from backend.nessie import get_nessie


def main():
    if config.NESSIE_MODE != "live":
        sys.exit("Set NESSIE_MODE=live first.")
    base = (sys.argv[1] if len(sys.argv) > 1 else config.PUBLIC_URL).rstrip("/")
    if not base.startswith("https://"):
        sys.exit("Give the public https URL, e.g. python -m scripts.register_nessie_hook https://abc.ngrok-free.app")
    n = get_nessie()
    for h in n.list_webhooks():
        if h.get("mode") == "decision" and "transfer" in (h.get("kinds") or []):
            n.delete_webhook(h["id"])
            print("removed old decision hook", h["id"], h.get("url"))
    hook = n.create_webhook({"mode": "decision", "url": f"{base}/webhooks/nessie-decision", "kinds": ["transfer"],
                             "max_wait_seconds": 300, "on_error": "decline"})
    print("registered:", hook.get("id"), hook.get("url"))
    print("\nAdd to .env, then restart the server:")
    print(f"NESSIE_HOOK_SECRET={hook.get('secret', '')}")
    print("NESSIE_HOLD=hook")
    print("\nTest it: python -c \"from backend.nessie import get_nessie; print(get_nessie().list_webhooks())\"")


if __name__ == "__main__":
    main()
