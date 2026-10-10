"""Create (or update env vars of) the Alex web service on Render. Secrets are read from local files.

  python scripts/render_deploy.py create
  python scripts/render_deploy.py env      # push env vars to the existing service
"""
import sys
from pathlib import Path

from render_api import call

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "workspace" / "secrets"
OWNER = "tea-da39cv3ncjis73c2nfog"
NAME = "alexreview-ai"


def fireworks_key() -> str:
    env = ROOT / "evals" / "aacr" / "aacr-bench" / "evaluation" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("OCR_LLM_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Fireworks key not found")


def env_vars() -> list:
    pem = sorted(SECRETS.glob("*.pem"))[-1].read_text(encoding="utf-8").strip()
    values = {
        "ALEX_APP_ID": "5263028",
        "ALEX_ALLOWED_ACCOUNTS": "niihhhall",
        "ALEX_APP_PRIVATE_KEY": pem,
        "ALEX_WEBHOOK_SECRET": (SECRETS / "webhook-secret.txt").read_text().strip(),
        "ALEX_LLM_API_KEY": fireworks_key(),
        "ALEX_LLM_URL": "https://api.fireworks.ai/inference/v1",
        "ALEX_MODEL": "accounts/fireworks/models/deepseek-v4p1-flash",
        "ALEX_TOKEN_BUDGET": "1500000",
        "ALEX_MONTHLY_TOKEN_BUDGET": "200000000",
        "ALEX_WORKERS": "2",
        "ALEX_REVIEW_ON_PUSH": "false",
    }
    return [{"key": k, "value": v} for k, v in values.items()]


def find_service():
    status, body = call("GET", f"/services?name={NAME}&ownerId={OWNER}")
    for item in body or []:
        if item["service"]["name"] == NAME:
            return item["service"]
    return None


def create(plan: str) -> None:
    if find_service():
        raise SystemExit("service already exists")
    payload = {
        "type": "web_service",
        "name": NAME,
        "ownerId": OWNER,
        "repo": "https://github.com/niihhhall/alex-mvp",
        "branch": "main",
        "autoDeploy": "yes",
        "envVars": env_vars(),
        "serviceDetails": {
            "runtime": "docker",
            "plan": plan,
            "region": "oregon",
            "healthCheckPath": "/healthz",
            "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."},
        },
    }
    status, body = call("POST", "/services", payload)
    if status >= 300:
        print(status, body)
        raise SystemExit(1)
    svc = body["service"]
    print(f"created {svc['id']} | {svc['serviceDetails'].get('url')} | plan {svc['serviceDetails'].get('plan')}")


def push_env() -> None:
    svc = find_service()
    status, body = call("PUT", f"/services/{svc['id']}/env-vars", env_vars())
    print(status, "env vars updated" if status < 300 else body)


if __name__ == "__main__":
    if sys.argv[1] == "create":
        create(sys.argv[2] if len(sys.argv) > 2 else "standard")
    else:
        push_env()
