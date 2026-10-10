"""Smoke test a running Alex server with signed fake webhooks (no reviews are queued).

Usage: python scripts/smoke-server.py http://localhost:8080 <webhook-secret-file>
"""
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

base, secret = sys.argv[1].rstrip("/"), Path(sys.argv[2]).read_text().strip()


def post(event, payload, sign=True):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{base}/webhook", data=body, method="POST")
    req.add_header("X-GitHub-Event", event)
    req.add_header("Content-Type", "application/json")
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if sign else "0" * 64
    req.add_header("X-Hub-Signature-256", f"sha256={sig}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


inst = {"id": 1, "account": {"login": "niihhhall"}}
checks = [
    ("health", urllib.request.urlopen(f"{base}/healthz", timeout=10).status, 200),
    ("ping", post("ping", {"zen": "hi"})[0], 200),
    ("bad signature", post("ping", {}, sign=False)[0], 401),
    ("stranger account", post("pull_request", {"action": "opened", "installation": {"id": 1, "account": {"login": "evil"}}})[0], 200),
    ("closed PR ignored", post("pull_request", {"action": "closed", "installation": inst, "repository": {"full_name": "niihhhall/x"}, "pull_request": {"number": 1}})[0], 200),
]
ok = True
for name, got, want in checks:
    ok &= got == want
    print(f"{'PASS' if got == want else 'FAIL'}  {name}: {got}")
sys.exit(0 if ok else 1)
