#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import logging
import os
import json

from browser import ADPAgent
from config  import RESUME_DOWNLOAD_DIR
from backend import get_pending_candidates, update_status

log = logging.getLogger("adp_agent")


def main():
    print("\n" + "=" * 50)
    print("  ADP Candidate Agent (Backend API mode)")
    print("=" * 50 + "\n")

    # 🔥 Fetch from backend instead of sheets
    candidates = get_pending_candidates()

    if not candidates:
        print("No pending candidates to process.")
        print("__RESULT__:" + json.dumps({
            "processed": [],
            "not_found": [],
            "errors": [],
            "resume_dir": RESUME_DOWNLOAD_DIR,
        }))
        return

    print(f"{len(candidates)} pending candidate(s)\n")

    processed = []
    not_found = []
    errors    = []

    agent = ADPAgent()

    try:
        agent.start()

        if not agent.login():
            log.warning("Login issue detected")

        time.sleep(3)

        if not agent.go_to_candidates():
            log.warning("Candidates tab not reached")

        for i, cand in enumerate(candidates, 1):

            name     = cand["candidateName"]
            email_id = cand["emailId"]

            print(f"\n-- [{i}/{len(candidates)}] {name} --")

            try:
                if agent.search(name):

                    resume_path = agent.download_resume(name, email_id)

                    if resume_path:
                        filename = os.path.basename(resume_path)

                        processed.append({
                            "candidate": name,
                            "file": filename,
                            "path": resume_path,
                        })

                        # ✅ Update backend
                        update_candidate(email_id, {
                            "status": "processed",
                            "aiScore": 0,
                            "aiRecommendation": "PENDING",
                            "aiSummary": f"Resume downloaded: {filename}"
                        })

                    else:
                        processed.append({
                            "candidate": name,
                            "file": None,
                            "path": None,
                        })

                        update_candidate(email_id, {
                            "status": "processed",
                            "aiRecommendation": "PENDING",
                            "aiSummary": "No resume found"
                        })

                    agent.clear_search()

                else:
                    not_found.append(name)

                    update_candidate(email_id, {
                        "status": "not_found",
                        "aiRecommendation": "REJECT",
                        "aiSummary": "Candidate not found in ADP"
                    })

            except Exception as e:
                errors.append(name)
                log.error(f"Error processing {name}: {e}")

                update_candidate(email_id, {
                    "status": "error",
                    "aiRecommendation": "REJECT",
                    "aiSummary": str(e)
                })

            agent.screenshot(f"candidate_{i}")

            if i < len(candidates):
                time.sleep(2)

    finally:
        agent.stop()

    print("\nDone.")

    # ✅ IMPORTANT: server.py depends on this format
    print("__RESULT__:" + json.dumps({
        "processed": processed,
        "not_found": not_found,
        "errors": errors,
        "resume_dir": RESUME_DOWNLOAD_DIR,
    }))


if __name__ == "__main__":
    main()
