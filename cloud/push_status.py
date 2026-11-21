"""Push a worker's status.json, run.json and rl_log.jsonl to branch status-<job> (GitHub contents API).

Run in a loop next to rl_job.py so the dashboard sees progress while the job runs.
    GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo python cloud/push_status.py out/<job>
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main():
    out = Path(sys.argv[1])
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = f"status-{out.name}"
    if call("GET", f"/repos/{repo}/git/ref/heads/{branch}") is None:
        main_sha = call("GET", f"/repos/{repo}/git/ref/heads/main")["object"]["sha"]
        call("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": main_sha})
    for name in ("status.json", "run.json", "rl_log.jsonl"):
        f = out / name
        if not f.exists():
            continue
        data = f.read_bytes()
        if name == "rl_log.jsonl" and len(data) > 900_000:
            data = b"\n".join(data.splitlines()[-3000:]) + b"\n"
        path = f"/repos/{repo}/contents/status/{out.name}/{name}"
        cur = call("GET", f"{path}?ref={branch}")
        body = {"message": f"status {out.name}", "branch": branch, "content": base64.b64encode(data).decode()}
        if cur and "sha" in cur:
            body["sha"] = cur["sha"]
        for _ in range(3):
            try:
                call("PUT", path, body)
                break
            except urllib.error.HTTPError as e:
                if e.code in (409, 422):
                    cur = call("GET", f"{path}?ref={branch}")
                    if cur and "sha" in cur:
                        body["sha"] = cur["sha"]
                    continue
                raise


if __name__ == "__main__":
    main()
