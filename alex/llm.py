"""Minimal OpenAI-compatible chat client (stdlib only)."""
import json
import re
import time
import urllib.error
import urllib.request
from typing import List, Optional


class LLMError(Exception):
    pass


def chat(messages: List[dict], *, url: str, api_key: str, model: str,
         json_mode: bool = True, temperature: float = 0.2, max_tokens: int = 4000,
         timeout: int = 180, retries: int = 2) -> dict:
    """Return {"content": str, "usage": dict}."""
    endpoint = url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")
    last_error = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {"content": data["choices"][0]["message"].get("content") or "", "usage": data.get("usage", {})}
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            last_error = LLMError(f"HTTP {err.code}: {detail}")
            if err.code in (400, 401, 403, 404):
                break
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as err:
            last_error = LLMError(str(err))
        time.sleep(3 * (attempt + 1))
    raise last_error or LLMError("unknown error")


def parse_json(content: str) -> Optional[dict]:
    """Parse a JSON object even if the model wrapped it in prose or code fences."""
    if not content:
        return None
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else None
    except ValueError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(content[start:end + 1])
        return value if isinstance(value, dict) else None
    except ValueError:
        return None
