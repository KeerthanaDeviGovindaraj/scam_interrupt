"""Every message is logged to SQLite (the web phone simulator reads it) and,
in PHOTON_MODE=live, also sent through Photon 2.0."""
import json
import logging

from . import config, db
from . import photon_adapter

log = logging.getLogger("messaging")


def send(owner_id: str, text: str, transfer_id=None, options=None) -> dict:
    options = options or []
    msg_id = db.ex("INSERT INTO messages (owner_id,direction,text,options,transfer_id,created_at) VALUES (?,?,?,?,?,?)",
                   (owner_id, "out", text, json.dumps(options), transfer_id, db.now()))
    delivered_via = "simulator"
    if config.PHOTON_MODE == "live":
        person = db.q1("SELECT phone FROM customers WHERE id=?", (owner_id,))
        try:
            if options:
                photon_adapter.send_choices(person["phone"], text, options)
            else:
                photon_adapter.send_text(person["phone"], text)
            delivered_via = "photon"
        except Exception as e:  # keep the demo alive; the simulator still shows it
            log.warning("Photon send failed (%s); message kept in simulator", e)
    return {"id": msg_id, "via": delivered_via}


def record_inbound(owner_id: str, text: str, transfer_id=None) -> None:
    db.ex("INSERT INTO messages (owner_id,direction,text,options,transfer_id,created_at) VALUES (?,?,?,?,?,?)",
          (owner_id, "in", text, "[]", transfer_id, db.now()))


def inbox(owner_id: str, limit: int = 50):
    return db.q("SELECT * FROM messages WHERE owner_id=? ORDER BY id DESC LIMIT ?", (owner_id, limit))[::-1]
