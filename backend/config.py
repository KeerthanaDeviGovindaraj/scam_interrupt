"""Settings loaded from environment variables (.env supported)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


NESSIE_MODE = env("NESSIE_MODE", "mock").lower()          # mock | live (Nessie v2)
NESSIE_KEY = env("NESSIE_KEY")
NESSIE_BASE = (env("NESSIE_URL") or env("NESSIE_BASE") or "https://v2-prod-api.nessieisreal.com").rstrip("/")

PHOTON_MODE = env("PHOTON_MODE", "sim").lower()            # sim | live
PHOTON_API_KEY = env("PHOTON_API_KEY")

MODEL = env("MODEL")
AGENT_MODEL = env("AGENT_MODEL") or MODEL   # model for the deepagents planner                                       # empty = rule-based
AGENT_MODE = env("AGENT_MODE", "pipeline").lower()          # pipeline | deepagents
# true = app acts instantly; the deepagents planner reviews and documents in the background
AGENT_BACKGROUND = env("AGENT_BACKGROUND", "true").lower() in ("1", "true", "yes")

MARY_PHONE = env("MARY_PHONE", "+15550000001")
DAVID_PHONE = env("DAVID_PHONE", "+15550000002")

DB_PATH = env("DB_PATH", "data/scam_interrupt.db")
MOCK_NESSIE_PATH = env("MOCK_NESSIE_PATH", "data/mock_nessie.json")

# Upgrades
FOLLOW_UP = env("FOLLOW_UP", "true").lower() in ("1", "true", "yes")      # adaptive follow-up question
NESSIE_HOLD = env("NESSIE_HOLD", "app").lower()                           # app | hook (Nessie decision hooks)
NESSIE_HOOK_SECRET = env("NESSIE_HOOK_SECRET")
PUBLIC_URL = env("PUBLIC_URL")                                             # e.g. https://abc.ngrok-free.app

# Risk thresholds
RISK_HIGH = 50       # score >= this -> hold + safety check
