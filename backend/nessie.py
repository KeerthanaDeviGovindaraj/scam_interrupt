"""Capital One Nessie client.

live -> Nessie v2 (https://v2-prod-api.nessieisreal.com), key sent as a Bearer token,
        amounts in cents. Confirmed endpoints: POST /data/seed, GET /accounts,
        POST /accounts/{id}/transfers {"amount_cents", "payee_id"}.
        Everything else is tried carefully and falls back if the endpoint differs.
mock -> offline stand-in with the same methods (no key, no Wi-Fi needed).
"""
import json
import logging
import os
import uuid
from datetime import date

import requests

from . import config

log = logging.getLogger("nessie")


class NessieError(RuntimeError):
    pass


def _items(data):
    """Accept a plain list or common wrappers like {"data": [...]}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "items", "results", "accounts", "customers", "merchants", "transactions", "transfers"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def oid(obj) -> str:
    return str(obj.get("id") or obj.get("_id") or "")


def dollars(obj) -> float:
    if obj.get("amount_cents") is not None:
        return int(obj["amount_cents"]) / 100
    return float(obj.get("amount", 0))


class LiveNessieV2:
    def __init__(self, key: str, base: str):
        if not key:
            raise NessieError("NESSIE_KEY is empty. Set it in .env or use NESSIE_MODE=mock.")
        self.base = base
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _req(self, method, path, body=None):
        r = requests.request(method, f"{self.base}{path}", headers=self.headers, json=body, timeout=20)
        if r.status_code >= 400:
            raise NessieError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text.strip() else {}

    def _try_get(self, *paths):
        for p in paths:
            try:
                return _items(self._req("GET", p))
            except NessieError as e:
                log.info("Nessie: %s", e)
        return []

    # ----- confirmed -----
    def seed_demo_bank(self):
        return self._req("POST", "/data/seed")

    def list_accounts(self):
        return _items(self._req("GET", "/accounts"))

    def create_transfer(self, account_id, payee_account_id, amount, description=""):
        body = {"amount_cents": int(round(float(amount) * 100)), "payee_id": payee_account_id}
        if description:
            body["description"] = description
        try:
            return self._req("POST", f"/accounts/{account_id}/transfers", body)
        except NessieError:
            if "description" in body:      # in case v2 rejects unknown fields
                body.pop("description")
                return self._req("POST", f"/accounts/{account_id}/transfers", body)
            raise

    # ----- customers, accounts, money in, bills (from the v2 OpenAPI spec) -----
    ADDRESS = {"street_number": "1", "street_name": "Nassau St", "city": "Princeton", "state": "NJ", "zip": "08540"}

    def find_customer(self, first, last):
        for c in self._try_get("/customers?limit=100"):
            if c.get("first_name") == first and c.get("last_name") == last:
                return c
        return None

    def create_customer(self, first, last):
        return self._req("POST", "/customers", {"first_name": first, "last_name": last, "address": self.ADDRESS})

    def customer_accounts(self, customer_id):
        return self._try_get(f"/customers/{customer_id}/accounts")

    def create_account(self, customer_id, nickname, balance):
        return self._req("POST", f"/customers/{customer_id}/accounts",
                         {"type": "Checking", "nickname": nickname[:40], "balance_cents": int(round(float(balance) * 100))})

    def get_account(self, account_id):
        return self._req("GET", f"/accounts/{account_id}")

    def deposit(self, account_id, amount, description="Deposit"):
        tx = self._req("POST", f"/accounts/{account_id}/deposits",
                       {"amount_cents": int(round(float(amount) * 100)), "description": description})
        try:
            self._req("POST", f"/transactions/{oid(tx)}/settle")   # skip the pending window for the demo
        except NessieError:
            pass
        return tx

    def list_bills(self, account_id):
        return self._try_get(f"/accounts/{account_id}/bills")

    def create_bill(self, account_id, payee, amount, nickname="", recurring_date=1):
        return self._req("POST", f"/accounts/{account_id}/bills",
                         {"status": "recurring", "payee": payee, "nickname": nickname or payee,
                          "payment_amount": float(amount), "recurring_date": int(recurring_date)})

    # ----- best effort (check the docs; these fall back safely) -----
    def list_customers(self):
        return self._try_get("/customers")

    def list_merchants(self):
        return self._try_get("/merchants")

    def list_transfers(self, account_id):
        return self._try_get(f"/accounts/{account_id}/transactions")

    def list_purchases(self, account_id):
        return []   # v2 has no purchase list; purchases appear in /accounts/{id}/transactions

    def create_purchase(self, account_id, merchant_id, amount, description="", purchase_date=None):
        body = {"amount_cents": int(round(float(amount) * 100)), "merchant_id": merchant_id}
        return self._req("POST", f"/accounts/{account_id}/purchases", body)

    # ----- decisions and webhooks (Nessie v2) -----
    def decide(self, tx_id, decision, reason=""):
        return self._req("POST", f"/transactions/{tx_id}/decision", {"decision": decision, "reason": (reason or "")[:200]})

    def get_transaction(self, tx_id):
        return self._req("GET", f"/transactions/{tx_id}")

    def list_webhooks(self):
        return _items(self._req("GET", "/webhooks"))

    def create_webhook(self, body):
        return self._req("POST", "/webhooks", body)

    def delete_webhook(self, hook_id):
        return self._req("DELETE", f"/webhooks/{hook_id}")


class MockNessie:
    """Offline fake with the same interface. Data persists in a JSON file."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            self._save({"customers": {}, "accounts": {}, "merchants": {}, "purchases": [], "transfers": [], "bills": []})

    def _load(self):
        with open(self.path) as f:
            return json.load(f)

    def _save(self, d):
        with open(self.path, "w") as f:
            json.dump(d, f, indent=1)

    def _new(self, kind, obj):
        d = self._load()
        obj["_id"] = uuid.uuid4().hex[:24]
        if isinstance(d[kind], dict):
            d[kind][obj["_id"]] = obj
        else:
            d[kind].append(obj)
        self._save(d)
        return obj

    def create_customer(self, first, last):
        return self._new("customers", {"first_name": first, "last_name": last})

    def create_account(self, customer_id, nickname, balance):
        return self._new("accounts", {"customer_id": customer_id, "nickname": nickname, "balance": balance})

    def create_merchant(self, name, category):
        return self._new("merchants", {"name": name, "category": category})

    def create_purchase(self, account_id, merchant_id, amount, description="", purchase_date=None):
        return self._new("purchases", {"payer_id": account_id, "merchant_id": merchant_id, "amount": amount,
                                       "purchase_date": purchase_date or date.today().isoformat(),
                                       "description": description, "status": "executed"})

    def create_transfer(self, account_id, payee_account_id, amount, description=""):
        return self._new("transfers", {"payer_id": account_id, "payee_id": payee_account_id, "amount": amount,
                                       "transaction_date": date.today().isoformat(),
                                       "description": description, "status": "executed"})

    def list_purchases(self, account_id):
        return [p for p in self._load()["purchases"] if p["payer_id"] == account_id]

    def list_transfers(self, account_id):
        return [t for t in self._load()["transfers"] if t["payer_id"] == account_id]

    def mark_history(self):
        """Everything created so far is past history, already reflected in the opening balance."""
        d = self._load()
        for t in d["purchases"] + d["transfers"]:
            t["history"] = True
        self._save(d)

    def get_account(self, account_id):
        d = self._load()
        a = d["accounts"].get(account_id)
        if not a:
            return None
        spent = sum(float(t["amount"]) for t in d["purchases"] + d["transfers"]
                    if t["payer_id"] == account_id and not t.get("history"))
        avail = float(a["balance"]) - spent
        return {"id": account_id, "available_cents": int(round(avail * 100)), "balance_cents": int(round(avail * 100))}

    def deposit(self, account_id, amount, description="Deposit"):
        d = self._load(); d["accounts"][account_id]["balance"] = float(d["accounts"][account_id]["balance"]) + float(amount)
        self._save(d)

    def create_bill(self, account_id, payee, amount, nickname="", recurring_date=1, due=None):
        return self._new("bills", {"account_id": account_id, "payee": payee, "nickname": nickname or payee,
                                   "payment_amount": float(amount), "status": "recurring",
                                   "upcoming_payment_date": due or ""})

    def list_bills(self, account_id):
        return [b for b in self._load().get("bills", []) if b["account_id"] == account_id]


    def decide(self, tx_id, decision, reason=""):
        d = self._load(); d.setdefault("decisions", []).append({"tx": tx_id, "decision": decision, "reason": reason})
        self._save(d)
        return {"id": tx_id, "decision": decision}

    def list_webhooks(self):
        return []

    def create_webhook(self, body):
        return {"id": "hook_mock", "secret": "mock_secret", **body}

    def delete_webhook(self, hook_id):
        return {}


_client = None


def get_nessie():
    global _client
    if _client is None:
        if config.NESSIE_MODE == "live":
            _client = LiveNessieV2(config.NESSIE_KEY, config.NESSIE_BASE)
        else:
            _client = MockNessie(config.MOCK_NESSIE_PATH)
    return _client


def reset_client():
    global _client
    _client = None
