"""GitHub App authentication: app JWT (RS256 via openssl) and installation tokens."""
import base64
import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

from .github_api import GitHub


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def normalize_private_key(raw: str) -> str:
    """Accept a PEM as-is, with literal \\n escapes (env var dashboards), or base64-encoded."""
    value = (raw or "").strip().strip('"')
    if "\\n" in value and "\n" not in value:
        value = value.replace("\\n", "\n")
    if not value.startswith("-----BEGIN"):
        try:
            value = base64.b64decode(value).decode("utf-8").strip()
        except (ValueError, UnicodeDecodeError):
            pass
    if not value.startswith("-----BEGIN") or "PRIVATE KEY-----" not in value:
        raise ValueError("app private key is not a PEM private key")
    return value + "\n"


def sign_rs256(message: bytes, private_key_pem: str) -> bytes:
    openssl = os.environ.get("ALEX_OPENSSL", "openssl")
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(private_key_pem)
        os.chmod(path, 0o600)
        proc = subprocess.run([openssl, "dgst", "-sha256", "-sign", path], input=message,
                              capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"openssl signing failed: {proc.stderr.decode('utf-8', 'replace')[:200]}")
        return proc.stdout
    finally:
        os.remove(path)


def app_jwt(app_id: str, private_key_pem: str, now: Optional[int] = None) -> str:
    now = int(now if now is not None else time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)},
                                 separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    return f"{header}.{payload}.{_b64url(sign_rs256(signing_input, private_key_pem))}"


class AppAuth:
    """Caches installation tokens until shortly before they expire."""

    def __init__(self, app_id: str, private_key_pem: str, api: str = "https://api.github.com"):
        self.app_id = str(app_id)
        self.key = normalize_private_key(private_key_pem)
        self.api = api
        self._tokens: Dict[int, Tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._bot_login: Optional[str] = None

    def app_client(self) -> GitHub:
        return GitHub(app_jwt(self.app_id, self.key), "", self.api)

    def bot_login(self) -> str:
        if not self._bot_login:
            slug = self.app_client().request("GET", "/app")["slug"]
            self._bot_login = f"{slug}[bot]"
        return self._bot_login

    def installation_token(self, installation_id: int) -> str:
        with self._lock:
            cached = self._tokens.get(installation_id)
            if cached and cached[1] - time.time() > 300:
                return cached[0]
            data = self.app_client().request("POST", f"/app/installations/{installation_id}/access_tokens", {})
            expires = datetime.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
            expires_ts = (expires - datetime(1970, 1, 1)).total_seconds()
            self._tokens[installation_id] = (data["token"], expires_ts)
            return data["token"]

    def installation_for_repo(self, repo: str) -> int:
        return int(self.app_client().request("GET", f"/repos/{repo}/installation")["id"])
