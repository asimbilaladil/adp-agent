import os
import json
import subprocess
import threading
from fastapi import FastAPI

app = FastAPI()

_lock    = threading.Lock()
_running = False


@app.get("/health")
def health():
    return {"status": "ok", "busy": _running}


@app.post("/run-agent")
def run_agent():
    global _running

    if _running:
        return {
            "success": False,
            "busy":    True,
            "error":   "Agent is already running. Try again after the current run finishes.",
        }

    if not _lock.acquire(blocking=False):
        return {
            "success": False,
            "busy":    True,
            "error":   "Agent is already running.",
        }

    _running = True
    try:
        env = os.environ.copy()

        result = subprocess.run(
            ["python", "adp_agent.py"],
            capture_output=True,
            text=True,
            timeout=30000,
            env=env,
        )

        stdout = result.stdout

        # Parse the structured result emitted by adp_agent.py on the last line
        agent_result = {}
        for line in stdout.splitlines():
            if line.startswith("__RESULT__:"):
                try:
                    agent_result = json.loads(line[len("__RESULT__:"):])
                except Exception:
                    pass
                break

        # Build a clean list of only the files that were actually downloaded
        resume_files = [
            p["file"] for p in agent_result.get("processed", [])
            if p.get("file")
        ]

        return {
            "success":        result.returncode == 0,
            "busy":           False,
            "resume_files":   resume_files,          # <-- use this in n8n Read Files node
            "resume_dir":     agent_result.get("resume_dir", ""),
            "processed":      agent_result.get("processed",  []),
            "not_found":      agent_result.get("not_found",  []),
            "errors":         agent_result.get("errors",     []),
            "stdout":         stdout,
            "stderr":         result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "busy": False, "error": "Agent timed out."}
    except Exception as e:
        return {"success": False, "busy": False, "error": str(e)}
    finally:
        _running = False
        _lock.release()
