#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADP Candidate Agent v5
========================
Entry point. Reads candidates from Google Sheets,
drives the ADP browser agent, updates sheet status.

Run:
    python adp_agent.py

Dependencies:
    pip install playwright gspread google-auth python-dotenv
    playwright install chromium
"""
import time
import logging
import os
import json

from sheets  import read_candidates, update_status
from browser import ADPAgent
from config  import RESUME_DOWNLOAD_DIR

log = logging.getLogger("adp_agent")


def main():
    print("\n" + "=" * 50)
    print("  ADP Candidate Agent v5 (Google Sheets mode)")
    print("  Login + 2FA + Search + Resume Download")
    print("=" * 50 + "\n")

    candidates = read_candidates()
    if not candidates:
        print("No pending candidates to process. Exiting.")
        # Still emit a valid JSON result so server.py can parse it
        print("__RESULT__:" + json.dumps({
            "processed": [],
            "not_found": [],
            "errors": [],
            "resume_dir": RESUME_DOWNLOAD_DIR,
        }))
        return

    print(f"{len(candidates)} pending candidate(s):")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. {c['candidate_name']}  ->  {c['posting_name']}")
    print(f"\nResumes will be saved to: {RESUME_DOWNLOAD_DIR}\n")

    # Track results for structured output
    processed = []   # {"candidate": ..., "file": ..., "path": ...}
    not_found = []   # candidate names
    errors    = []   # candidate names

    agent = ADPAgent()
    try:
        agent.start()

        if not agent.login():
            log.warning("Login may have failed - check browser window")
        time.sleep(3)

        if not agent.go_to_candidates():
            log.warning("Could not reach Candidates tab automatically.")

        for i, cand in enumerate(candidates, 1):
            name     = cand["candidate_name"]
            email_id = cand["email_id"]
            print(f"\n-- [{i}/{len(candidates)}] {name} --")

            try:
                if agent.search(name):
                    resume_path = agent.download_resume(name, email_id)
                    if resume_path:
                        filename = os.path.basename(resume_path)
                        processed.append({
                            "candidate": name,
                            "file":      filename,
                            "path":      resume_path,
                        })
                        update_status(cand["_row"], f"Processed - Resume: {filename}")
                    else:
                        processed.append({
                            "candidate": name,
                            "file":      None,
                            "path":      None,
                        })
                        update_status(cand["_row"], "Processed - No Resume")
                    agent.clear_search()
                else:
                    not_found.append(name)
                    update_status(cand["_row"], "Not Found")

            except Exception as e:
                errors.append(name)
                log.error(f"  Error processing {name}: {e}")
                update_status(cand["_row"], "Error")

            agent.screenshot(f"candidate_{i}")
            if i < len(candidates):
                time.sleep(2)

        downloaded = sum(1 for p in processed if p["file"])
        print(f"\n{'=' * 50}")
        print(f"  Done!")
        print(f"  Found: {len(processed)}  |  Not Found: {len(not_found)}  |  Errors: {len(errors)}")
        print(f"  Resumes downloaded: {downloaded}")
        print(f"  Saved to: {RESUME_DOWNLOAD_DIR}")
        print(f"{'=' * 50}")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        agent.stop()

    # Emit structured result as the last line — server.py parses this
    print("__RESULT__:" + json.dumps({
        "processed":   processed,
        "not_found":   not_found,
        "errors":      errors,
        "resume_dir":  RESUME_DOWNLOAD_DIR,
    }))


if __name__ == "__main__":
    main()
