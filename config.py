"""
config.py - All settings loaded from .env
==========================================
Never hardcode credentials here.
"""
import os, sys, platform, logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

def _env(key, default=None, required=False):
    val = os.getenv(key, default)
    if required and not val:
        sys.exit(f"[config] Missing required env var: {key}  ->  add it to .env")
    return val

# ── Google Sheets ─────────────────────────────────────────────────────────────
GSHEET_ID             = _env("GSHEET_ID")
GSHEET_TAB            = _env("GSHEET_TAB", "candidates")
GSERVICE_ACCOUNT_JSON = _env("GSERVICE_ACCOUNT_JSON")

# ── ADP ───────────────────────────────────────────────────────────────────────
ADP_LOGIN_URL       = _env("ADP_LOGIN_URL", "https://workforcenow.adp.com/")
ADP_RECRUITMENT_URL = _env("ADP_RECRUITMENT_URL",
    "https://workforcenow.adp.com/theme/admin.html#/Process/ProcessTabTalentCategoryRecruitment")
ADP_USERNAME        = _env("ADP_USERNAME")
ADP_PASSWORD        = _env("ADP_PASSWORD")

# ── Security Questions ────────────────────────────────────────────────────────
SECURITY_QUESTIONS = {
    "childhood best friend": _env("SECURITY_Q_CHILDHOOD_BEST_FRIEND", ""),
    "childhood nickname":    _env("SECURITY_Q_CHILDHOOD_NICKNAME", ""),
    "mother born":           _env("SECURITY_Q_MOTHER_BORN", ""),
}

# ── Gmail ─────────────────────────────────────────────────────────────────────
GMAIL_ADDRESS  = _env("GMAIL_ADDRESS")
GMAIL_PASSWORD = _env("GMAIL_PASSWORD")

# ── Browser ───────────────────────────────────────────────────────────────────
EXTENSION_PATH = _env("EXTENSION_PATH")

_default_profile = (r"D:\hr-ai-agent\.browser-profile" if platform.system() == "Windows"
                    else str(BASE_DIR / ".browser-profile"))

BROWSER_PROFILE_DIR = _env("BROWSER_PROFILE_DIR", _default_profile)
SCREENSHOT_DIR      = _env("SCREENSHOT_DIR",      str(BASE_DIR / "screenshots"))
RESUME_DOWNLOAD_DIR = _env("RESUME_DOWNLOAD_DIR", str(BASE_DIR / "resumes"))

# ── Timing (seconds) ─────────────────────────────────────────────────────────
WAIT_AFTER_LOGIN = int(_env("WAIT_AFTER_LOGIN",    "15"))
WAIT_AFTER_NAV   = int(_env("WAIT_AFTER_NAVIGATE", "2"))
SEARCH_WAIT      = int(_env("SEARCH_WAIT",          "3"))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
