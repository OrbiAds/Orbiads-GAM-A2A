"""One-shot OAuth helper — prove connectability with YOUR OrbiAds account.

Runs the standard MCP OAuth flow against orbiads.com/mcp:
  1) Dynamic Client Registration (RFC 7591) at /register
  2) authorization_code + PKCE (S256) via your browser  -> you consent with Google
  3) token exchange at /token  -> access_token (+ refresh_token)
Then appends ORBIADS_MCP_TOKEN (+ refresh) to .env.

Usage:
    python get_token.py
A browser opens; log in with jeanludovic.albany@gmail.com and approve.
"""

import base64
import hashlib
import http.server
import json
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

BASE = "https://orbiads.com/mcp"
AUTHORIZE = f"{BASE}/authorize"
TOKEN = f"{BASE}/token"
REGISTER = f"{BASE}/register"
REDIRECT = "http://localhost:8765/callback"
SCOPE = "openid https://www.googleapis.com/auth/userinfo.email"

_code_holder: dict[str, str] = {}


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _post_form(url: str, payload: dict) -> dict:
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        if "code" in params:
            _code_holder["code"] = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - you can close this tab and return to the terminal.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code in callback: " + qs.encode())

    def log_message(self, *args):  # silence
        pass


def main() -> None:
    # 1) Dynamic Client Registration
    print("1) Registering OAuth client (DCR)...")
    reg = _post_json(
        REGISTER,
        {
            "client_name": "orbiads-a2a-lab",
            "redirect_uris": [REDIRECT],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    client_id = reg["client_id"]
    client_secret = reg.get("client_secret")
    print(f"   client_id = {client_id}")

    # 2) PKCE + authorize
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    auth_url = AUTHORIZE + "?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    server = http.server.HTTPServer(("localhost", 8765), _Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    print("2) Opening browser for consent...")
    print("   If it doesn't open, paste this URL:\n   " + auth_url)
    webbrowser.open(auth_url)

    # wait for callback
    import time
    for _ in range(120):
        if "code" in _code_holder:
            break
        time.sleep(1)
    if "code" not in _code_holder:
        raise SystemExit("No authorization code received (timeout).")

    # 3) token exchange
    print("3) Exchanging code for tokens...")
    form = {
        "grant_type": "authorization_code",
        "code": _code_holder["code"],
        "redirect_uri": REDIRECT,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if client_secret:
        form["client_secret"] = client_secret
    tok = _post_form(TOKEN, form)
    access = tok["access_token"]
    refresh = tok.get("refresh_token", "")
    print(f"\nACCESS TOKEN (first 24): {access[:24]}...")
    print(f"REFRESH TOKEN present: {bool(refresh)}")

    with open(".env", "a", encoding="utf-8") as f:
        f.write(f"\nORBIADS_MCP_CLIENT_ID={client_id}\n")  # needed for headless refresh
        f.write(f"ORBIADS_MCP_TOKEN={access}\n")
        if refresh:
            f.write(f"ORBIADS_MCP_REFRESH_TOKEN={refresh}\n")
    print("\n.env updated with ORBIADS_MCP_TOKEN. Now run:")
    print("  uvicorn gam_sentinel.agent:a2a_app --host localhost --port 10000")


if __name__ == "__main__":
    main()
