"""Point the GitHub App's webhook at a URL, using the app's own JWT. Secrets come from workspace/secrets.

Usage: python scripts/set_app_webhook.py https://alexreview-ai.onrender.com/webhook
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ALEX_OPENSSL", r"C:\Program Files\Git\usr\bin\openssl.exe")

from alex.app_auth import AppAuth  # noqa: E402

secrets = ROOT / "workspace" / "secrets"
auth = AppAuth("5263028", sorted(secrets.glob("*.pem"))[-1].read_text(encoding="utf-8"))
gh = auth.app_client()
cfg = gh.request("PATCH", "/app/hook/config", {
    "url": sys.argv[1],
    "content_type": "json",
    "secret": (secrets / "webhook-secret.txt").read_text().strip(),
    "insecure_ssl": "0",
})
print("webhook url:", cfg.get("url"), "| content type:", cfg.get("content_type"), "| ssl verify:", cfg.get("insecure_ssl") == "0")
