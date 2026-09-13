"""
Resend's email API, standard library only. The key is passed in by the caller; nothing here stores it.

What Resend offers, verified live by experiments/scenario_email_tier3.py (results/scenarios/email_tier3.md):
  - POST /emails honors Idempotency-Key for 24h. The same key and body return the first email's id with
    Idempotent-Replayed: true and send nothing. The same key with another body is 409 invalid_idempotent_request.
  - GET /emails and GET /emails/{id} exist, but a sending-only API key gets 401 restricted_api_key.
  - probe(): Resend checks the key before it checks the sender's domain. A well-formed body from a domain nobody
    can verify returns 409 when the key was already used and 403 when it was not; neither sends anything. So even a
    sending-only key can ask "did an email go out under this key?", inside the 24h window and not after it.
"""
import json, time, urllib.error, urllib.request

API = "https://api.resend.com"
SENDER = "Interlock Sandbox <onboarding@resend.dev>"
TEST_INBOXES = ("delivered@resend.dev",)       # Resend's own test inbox; nothing else is ever sent to
PROBE_BODY = {"from": "Probe <probe@interlock-sandbox.invalid>", "to": ["delivered@resend.dev"],
              "subject": "probe", "text": "probe"}  # .invalid can never be verified, so this body never sends


class ResendError(RuntimeError):
    def __init__(self, status, name, message):
        super().__init__(f"Resend {status} {name}: {message}")
        self.status, self.name = status, name


def key_used(status, name, message=""):
    """A probe's answer: True (the key was used), False (never used). Anything else is not an answer, so raise."""
    if status == 409 and name == "invalid_idempotent_request":
        return True
    if status == 403 and name == "validation_error" and "not verified" in (message or ""):
        return False
    raise ResendError(status, name, f"probe got neither answer: {message}")


class Resend:
    def __init__(self, api_key, min_interval=0.6):
        if not api_key:
            raise ValueError("RESEND_API_KEY is not set")
        self._auth, self._gap, self._last = f"Bearer {api_key}", min_interval, 0.0

    def request(self, method, path, body=None, idempotency_key=None):
        """(status, json body, headers). HTTP errors come back as values."""
        for attempt in range(5):
            time.sleep(max(0.0, self._last + self._gap - time.time()))     # stay under Resend's rate limit
            self._last = time.time()
            req = urllib.request.Request(API + path, method=method,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={"Authorization": self._auth, "Content-Type": "application/json",
                                                  "User-Agent": "interlock-scenario-email-tier3"})
            if idempotency_key:
                req.add_header("Idempotency-Key", idempotency_key)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status, json.loads(r.read() or b"{}"), r.headers
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:       # refused before processing: safe to ask again
                    time.sleep(2 ** attempt)
                    continue
                return e.code, json.loads(e.read() or b"{}"), e.headers

    def send(self, email, idempotency_key):
        """(email id, replayed). replayed=True means Resend matched the key and sent nothing new."""
        if set(email["to"]) - set(TEST_INBOXES):
            raise ValueError("refusing to send: Resend test inboxes only")
        status, body, headers = self.request("POST", "/emails", email, idempotency_key)
        if status != 200:
            raise ResendError(status, body.get("name"), body.get("message"))
        return body["id"], headers.get("Idempotent-Replayed") == "true"

    def probe(self, idempotency_key):
        status, body, _ = self.request("POST", "/emails", PROBE_BODY, idempotency_key)
        return key_used(status, body.get("name"), body.get("message", ""))
