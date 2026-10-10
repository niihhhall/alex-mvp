import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from alex import app_auth
from alex.server import Usage, decide, is_trigger, verify_signature

ALLOWED = {"niihhhall"}


def pr_event(action="opened", assoc="OWNER", draft=False, account="niihhhall", user_type="User"):
    return {
        "action": action,
        "installation": {"id": 7, "account": {"login": account}},
        "repository": {"full_name": f"{account}/lab"},
        "pull_request": {"number": 3, "draft": draft, "author_association": assoc, "user": {"type": user_type}},
    }


def comment_event(body="/alex", assoc="OWNER", user_type="User", on_pr=True, action="created"):
    issue = {"number": 3}
    if on_pr:
        issue["pull_request"] = {"url": "x"}
    return {
        "action": action,
        "installation": {"id": 7, "account": {"login": "niihhhall"}},
        "repository": {"full_name": "niihhhall/lab"},
        "issue": issue,
        "comment": {"id": 99, "body": body, "author_association": assoc, "user": {"type": user_type}},
    }


class SignatureTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        body = b'{"a":1}'
        good = "sha256=" + hmac.new(b"s3cret-s3cret-s3cret", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature("s3cret-s3cret-s3cret", body, good))
        self.assertFalse(verify_signature("other-secret-value!!", body, good))
        self.assertFalse(verify_signature("s3cret-s3cret-s3cret", body, ""))
        self.assertFalse(verify_signature("", body, good))


class DecideTests(unittest.TestCase):
    def test_pr_opened_by_owner(self):
        job, _ = decide("pull_request", pr_event(), ALLOWED)
        self.assertEqual((job.repo, job.number, job.installation_id, job.comment_id), ("niihhhall/lab", 3, 7, None))

    def test_pr_ignored_cases(self):
        self.assertIsNone(decide("pull_request", pr_event(assoc="NONE"), ALLOWED)[0])
        self.assertIsNone(decide("pull_request", pr_event(assoc="CONTRIBUTOR"), ALLOWED)[0])
        self.assertIsNone(decide("pull_request", pr_event(draft=True), ALLOWED)[0])
        self.assertIsNone(decide("pull_request", pr_event(action="synchronize"), ALLOWED)[0])
        self.assertIsNone(decide("pull_request", pr_event(account="stranger"), ALLOWED)[0])
        self.assertIsNone(decide("pull_request", pr_event(user_type="Bot"), ALLOWED)[0])

    def test_review_on_push(self):
        self.assertIsNotNone(decide("pull_request", pr_event(action="synchronize"), ALLOWED, review_on_push=True)[0])

    def test_comment_triggers(self):
        job, _ = decide("issue_comment", comment_event(), ALLOWED)
        self.assertEqual(job.comment_id, 99)
        self.assertIsNotNone(decide("issue_comment", comment_event("@AlexReview-AI please"), ALLOWED)[0])

    def test_comment_ignored_cases(self):
        self.assertIsNone(decide("issue_comment", comment_event("looks good"), ALLOWED)[0])
        self.assertIsNone(decide("issue_comment", comment_event(assoc="NONE"), ALLOWED)[0])
        self.assertIsNone(decide("issue_comment", comment_event(user_type="Bot"), ALLOWED)[0])
        self.assertIsNone(decide("issue_comment", comment_event(on_pr=False), ALLOWED)[0])
        self.assertIsNone(decide("issue_comment", comment_event(action="edited"), ALLOWED)[0])

    def test_other_events(self):
        self.assertIsNone(decide("push", pr_event(), ALLOWED)[0])

    def test_trigger_words(self):
        self.assertTrue(is_trigger("  /Alex review this"))
        self.assertFalse(is_trigger("hey /alex"))


class UsageTests(unittest.TestCase):
    def test_cap(self):
        path = Path(tempfile.mkdtemp()) / "u.json"
        usage = Usage(path, 1000)
        self.assertFalse(usage.over_budget())
        usage.add(600)
        usage.add(500)
        self.assertEqual(usage.used(), 1100)
        self.assertTrue(usage.over_budget())
        self.assertFalse(Usage(path, 0).over_budget())


def _openssl():
    for cand in (os.environ.get("ALEX_OPENSSL"), shutil.which("openssl"), r"C:\Program Files\Git\usr\bin\openssl.exe"):
        if cand and Path(cand).exists():
            return cand
    return None


class AppAuthTests(unittest.TestCase):
    def test_normalize_key_forms(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
        self.assertEqual(app_auth.normalize_private_key(pem), pem + "\n")
        self.assertEqual(app_auth.normalize_private_key(pem.replace("\n", "\\n")), pem + "\n")
        self.assertEqual(app_auth.normalize_private_key(base64.b64encode(pem.encode()).decode()), pem + "\n")
        with self.assertRaises(ValueError):
            app_auth.normalize_private_key("not a key")

    @unittest.skipUnless(_openssl(), "openssl not available")
    def test_jwt_signature_verifies(self):
        openssl = _openssl()
        tmp = Path(tempfile.mkdtemp())
        key, pub = tmp / "k.pem", tmp / "p.pem"
        subprocess.run([openssl, "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
        subprocess.run([openssl, "rsa", "-in", str(key), "-pubout", "-out", str(pub)], check=True, capture_output=True)
        os.environ["ALEX_OPENSSL"] = openssl
        token = app_auth.app_jwt("5263028", key.read_text(), now=1_800_000_000)
        header, payload, sig = token.split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        claims = json.loads(base64.urlsafe_b64decode(pad(payload)))
        self.assertEqual(claims, {"iat": 1_799_999_940, "exp": 1_800_000_540, "iss": "5263028"})
        (tmp / "msg").write_bytes(f"{header}.{payload}".encode())
        (tmp / "sig").write_bytes(base64.urlsafe_b64decode(pad(sig)))
        check = subprocess.run([openssl, "dgst", "-sha256", "-verify", str(pub), "-signature", str(tmp / "sig"),
                                str(tmp / "msg")], capture_output=True, text=True)
        self.assertIn("Verified OK", check.stdout)


if __name__ == "__main__":
    unittest.main()
