"""SQLite storage. One connection per call keeps FastAPI threads safe."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    role TEXT NOT NULL,                 -- customer | family | payee
    nessie_customer_id TEXT,
    nessie_account_id TEXT,
    trusted_contact_id TEXT,            -- customers.id of the family member
    family_opt_in INTEGER DEFAULT 0     -- customer agreed to family alerts
);
CREATE TABLE IF NOT EXISTS merchants (
    id TEXT PRIMARY KEY,                -- Nessie merchant id
    name TEXT NOT NULL,
    category TEXT NOT NULL              -- grocery | pharmacy | gift_card | crypto | utility
);
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    payee_id TEXT NOT NULL,             -- Nessie account id OR merchant id
    payee_name TEXT NOT NULL,
    payee_kind TEXT NOT NULL,           -- account | merchant
    category TEXT DEFAULT 'transfer',
    amount REAL NOT NULL,
    hour INTEGER NOT NULL,
    status TEXT NOT NULL,               -- scoring | awaiting_customer | awaiting_family | held_review | released | cancelled
    risk_score INTEGER DEFAULT 0,
    risk_level TEXT DEFAULT 'low',
    reasons TEXT DEFAULT '[]',
    nessie_ref TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    transcript TEXT DEFAULT '',
    signals TEXT DEFAULT '[]',
    coached INTEGER,
    explanation TEXT,
    detector TEXT,                      -- llm | rules
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_id INTEGER NOT NULL,
    contact_id TEXT NOT NULL,
    message TEXT NOT NULL,
    decision TEXT,                      -- approve | cancel
    decided_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS habits (
    customer_id TEXT PRIMARY KEY,
    usual_payees TEXT DEFAULT '[]',
    avg_amount REAL DEFAULT 0,
    max_amount REAL DEFAULT 0,
    active_hours TEXT DEFAULT '[]',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS messages (     -- phone simulator + Photon log
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,             -- customers.id whose phone this is
    direction TEXT NOT NULL,            -- out (agent -> person) | in (person -> agent)
    text TEXT NOT NULL,
    options TEXT DEFAULT '[]',          -- e.g. ["Approve","Cancel"]
    transfer_id INTEGER,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


MIGRATIONS = [
    "ALTER TABLE checks ADD COLUMN followup_question TEXT",
    "ALTER TABLE checks ADD COLUMN followup_answer TEXT",
    "ALTER TABLE checks ADD COLUMN scam_type TEXT",
    "ALTER TABLE transfers ADD COLUMN scam_type TEXT",
]


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)
        for m in MIGRATIONS:
            try:
                c.execute(m)
            except sqlite3.OperationalError:
                pass  # column already exists


def reset_db():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    init_db()


def row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("reasons", "signals", "options", "usual_payees", "active_hours"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


def q(sql, params=()):
    with connect() as c:
        return [row(r) for r in c.execute(sql, params).fetchall()]


def q1(sql, params=()):
    with connect() as c:
        return row(c.execute(sql, params).fetchone())


def ex(sql, params=()):
    with connect() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def kv_set(key: str, value) -> None:
    ex("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, json.dumps(value)))


def kv_get(key: str, default=None):
    r = q1("SELECT value FROM kv WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default
