"""Capital One Nessie client.

live mode talks to the real API (get a key at v2.nessieisreal.com).
mock mode is an offline stand-in with the same methods, so you can build
before your key works and keep demoing if Wi-Fi drops.

VERIFY field names against the Nessie docs before relying on live mode.
"""
import json
import os
import uuid
from datetime import date

import requests

from . import config

ADDRESS = {"street_number": "1", "street_name": "Nassau St", "city": "Princeton",
           "state": "NJ", "zip": "08540"}


class NessieError(RuntimeError):
    pass


class LiveNessie:
    def __init__(self, key: str, base: str):
        if not key:
            raise NessieError("NESSIE_KEY is empty. Set it in .env or use NESSIE_MODE=mock.")
        self.key, self.base = key, base

    def _url(self, path):
        return f"{self.base}{path}?key={self.key}"

    def _post(self, path, body):
        r = requests.post(self._url(path), json=body, timeout=15)
        if r.status_code >= 400:
            raise NessieError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
        data = r.json()
        return data.get("objectCreated", data)

    def _get(self, path):
        r = requests.get(self._url(path), timeout=15)
        if r.status_code >= 400:
            raise NessieError(f"GET {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def create_customer(self, first, last):
        return self._post("/customers", {"first_name": first, "last_name": last, "address": ADDRESS})

    def create_account(self, customer_id, nickname, balance):
        return self._post(f"/customers/{customer_id}/accounts",
                          {"type": "Checking", "nickname": nickname, "rewards": 0, "balance": balance})

    def create_merchant(self, name, category):
        return self._post("/merchants", {"name": name, "category": category, "address": ADDRESS,
                                         "geocode": {"lat": 40.35, "lng": -74.66}})

    def create_purchase(self, account_id, merchant_id, amount, description="", purchase_date=None):
        return self._post(f"/accounts/{account_id}/purchases",
                          {"merchant_id": merchant_id, "medium": "balance", "amount": amount,
                           "purchase_date": purchase_date or date.today().isoformat(),
                           "description": description})

    def create_transfer(self, account_id, payee_account_id, amount, description=""):
        return self._post(f"/accounts/{account_id}/transfers",
                          {"medium": "balance", "payee_id": payee_account_id, "amount": amount,
                           "transaction_date": date.today().isoformat(), "description": description})

    def list_purchases(self, account_id):
        return self._get(f"/accounts/{account_id}/purchases")

    def list_transfers(self, account_id):
        return self._get(f"/accounts/{account_id}/transfers")


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
            _client = LiveNessie(config.NESSIE_KEY, config.NESSIE_BASE)
        else:
            _client = MockNessie(config.MOCK_NESSIE_PATH)
    return _client


def reset_client():
    global _client
    _client = None
