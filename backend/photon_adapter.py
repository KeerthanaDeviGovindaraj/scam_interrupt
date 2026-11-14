"""Photon 2.0 adapter.

Messages really go through Photon 2.0 (required for the Photon tracks). The
TypeScript bridge in photon-bridge/ (spectrum-ts, iMessage) does the sending;
this file just asks the bridge to send.
"""
import os

import requests

BRIDGE_URL = os.environ.get("PHOTON_BRIDGE_URL", "http://127.0.0.1:8787").rstrip("/")


class PhotonNotConfigured(RuntimeError):
    pass


def send_text(phone: str, text: str) -> None:
    try:
        r = requests.post(f"{BRIDGE_URL}/send", json={"to": phone, "text": text}, timeout=15)
    except requests.RequestException as e:
        raise PhotonNotConfigured(f"Photon bridge not reachable at {BRIDGE_URL}: {e}") from e
    if r.status_code != 200:
        raise PhotonNotConfigured(f"Photon bridge error {r.status_code}: {r.text[:200]}")


def send_choices(phone: str, text: str, options: list[str]) -> None:
    """Approve/Cancel for the family alert, as reply words (handled in app.py's webhook)."""
    send_text(phone, text + "\n\nReply " + " or ".join(o.upper() for o in options) + ".")
