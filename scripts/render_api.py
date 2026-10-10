"""Tiny Render API helper. Reads the key from workspace/secrets/render-api-key.txt (never printed).

  python scripts/render_api.py GET /owners
  python scripts/render_api.py POST /services payload.json
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "workspace" / "secrets" / "render-api-key.txt").read_text().strip()


def call(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"https://api.render.com/v1{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {KEY}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()[:2000]


if __name__ == "__main__":
    method, path = sys.argv[1], sys.argv[2]
    payload = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if len(sys.argv) > 3 else None
    status, body = call(method, path, payload)
    print(status)
    print(json.dumps(body, indent=1) if not isinstance(body, str) else body)
