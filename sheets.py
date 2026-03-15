"""
sheets.py - Google Sheets helpers
===================================
Read pending candidates, update row status.
"""
import logging
import sys

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    sys.exit("Run: pip install gspread google-auth")

from config import GSHEET_ID, GSHEET_TAB, GSERVICE_ACCOUNT_JSON

log = logging.getLogger("adp_agent")

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_sheet():
    creds = Credentials.from_service_account_file(GSERVICE_ACCOUNT_JSON, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(GSHEET_ID).worksheet(GSHEET_TAB)


def read_candidates():
    """Return list of dicts for every row with status='pending'."""
    log.info("Reading candidates from Google Sheet...")
    sheet = _get_sheet()
    candidates = []

    for idx, row in enumerate(sheet.get_all_records(), start=2):
        status   = str(row.get("status",         "")).strip().lower()
        name     = str(row.get("candidate_name", "")).strip()
        email_id = str(row.get("email_id",       "")).strip()

        if not name:
            continue
        if not email_id:
            log.warning(f"  Skip (missing email_id): {name}"); continue
        if status in ("processed", "done", "not found", "error"):
            log.info(f"  Skip ({status}): {name}");             continue
        if status != "pending":
            log.info(f"  Skip (unknown status '{status}'): {name}"); continue

        candidates.append({
            "_row":           idx,
            "posting_name":   str(row.get("posting_name",   "")).strip(),
            "candidate_name": name,
            "date_applied":   str(row.get("date_applied",   "")).strip(),
            "hiring_manager": str(row.get("hiring_manager", "")).strip(),
            "recruiter":      str(row.get("recruiter",      "")).strip(),
            "status":         status,
            "email_id":       email_id,
        })

    log.info(f"Found {len(candidates)} pending candidate(s).")
    return candidates


def update_status(sheet_row: int, status: str):
    """Write status string to the 'status' column of the given row."""
    try:
        sheet   = _get_sheet()
        headers = sheet.row_values(1)
        if "status" not in headers:
            log.error("'status' column not found in sheet!"); return
        sheet.update_cell(sheet_row, headers.index("status") + 1, status)
        log.info(f"  Sheet row {sheet_row} -> {status}")
    except Exception as e:
        log.error(f"  Failed to update sheet row {sheet_row}: {e}")
