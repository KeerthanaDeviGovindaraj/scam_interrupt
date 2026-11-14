"""Photon 2.0 adapter. THIS IS THE ONE FILE TO FINISH WITH PHOTON'S DOCS.

Required for the Photon tracks: messages must really go through Photon 2.0
(photon.codes/beta). A substitute like Twilio makes you ineligible.

Steps (from the playbook):
 1. Read Photon's hackathon guidelines page (link in the hacker packet).
 2. Fill in send_text() and send_choices() with their SDK or API.
 3. Find out how replies reach you. If Photon calls a webhook, point it at
    POST /webhooks/photon on a public URL (deployed server or a tunnel such as ngrok).
    Then map their payload in app.py -> photon_webhook() to {"from": phone, "text": text}.
 4. Voice: if Photon supports voice calls, add start_voice_check(); otherwise
    keep the text safety check (playbook fallback).
"""
from . import config


class PhotonNotConfigured(RuntimeError):
    pass


def send_text(phone: str, text: str) -> None:
    if not config.PHOTON_API_KEY:
        raise PhotonNotConfigured("Set PHOTON_API_KEY and implement send_text() per Photon's docs.")
    # TODO: call Photon 2.0 here, e.g. photon_client.send(to=phone, text=text)
    raise PhotonNotConfigured("send_text() not implemented yet")


def send_choices(phone: str, text: str, options: list[str]) -> None:
    """Approve/Cancel for the family alert. If Photon supports buttons or an
    interactive card, use it; otherwise send text and ask them to reply with a word."""
    send_text(phone, text + "\n\nReply " + " or ".join(o.upper() for o in options) + ".")
