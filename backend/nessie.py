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

    # ----- best effort (check the docs; these fall back safely) -----
    def list_customers(self):
        return self._try_get("/customers")

    def list_merchants(self):
        return self._try_get("/merchants")

    def list_transfers(self, account_id):
        return self._try_get(f"/accounts/{account_id}/transfers", f"/accounts/{account_id}/transactions")

    def list_purchases(self, account_id):
        return self._try_get(f"/accounts/{account_id}/purchases")

    def create_purchase(self, account_id, merchant_id, amount, description="", purchase_date=None):
        body = {"amount_cents": int(round(float(amount) * 100)), "merchant_id": merchant_id}
        return self._req("POST", f"/accounts/{account_id}/purchases", body)


class MockNessie:
    """Offline fake with the same interface. Data persists in a JSON file."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            self._save({"customers": {}, "accounts": {}, "merchants": {}, "purchases": [], "transfers": []})

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
