import requests
import os

BASE_URL = os.getenv("BACKEND_URL", "https://hr-api.aygfoods.com")
API_KEY  = os.getenv("N8N_API_KEY")

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}


def get_pending_candidates():
    res = requests.get(
        f"{BASE_URL}/api/candidates?status=pending",
        headers=HEADERS
    )
    res.raise_for_status()
    return res.json().get("data", [])


def update_candidate(email_id, payload):
    res = requests.patch(
        f"{BASE_URL}/api/candidates/{email_id}/ai-review",
        json=payload,
        headers=HEADERS
    )
    res.raise_for_status()
    return res.json()
