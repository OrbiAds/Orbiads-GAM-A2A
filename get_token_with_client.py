"""Utilise un client OAuth CRÉÉ DEPUIS LA PAGE OrbiAds (pas de DCR) pour obtenir un token,
puis appelle le MCP OrbiAds — preuve que l'agent créé par l'utilisateur fonctionne.

Usage :
    ORBIADS_CLIENT_ID=<client_id de la page>  [ORBIADS_CLIENT_SECRET=<secret>] \
    python get_token_with_client.py
Le Redirect URI de l'agent (sur la page) DOIT être http://localhost:8765/callback.
"""
import asyncio
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request

BASE = "https://orbiads.com/mcp"
REDIRECT = "http://localhost:8765/callback"
SCOPE = "openid https://www.googleapis.com/auth/userinfo.email"
CLIENT_ID = os.environ["ORBIADS_CLIENT_ID"]
CLIENT_SECRET = os.environ.get("ORBIADS_CLIENT_SECRET", "")
_hold: dict[str, str] = {}


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in q:
            _hold["code"] = q["code"][0]
            self.send_response(200); self.end_headers()
            self.wfile.write(b"OK - retourne au terminal.")
        else:
            self.send_response(400); self.end_headers()

    def log_message(self, *a):
        pass


def main():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = BASE + "/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
        "scope": SCOPE, "state": secrets.token_urlsafe(8),
        "code_challenge": challenge, "code_challenge_method": "S256"})
    threading.Thread(target=http.server.HTTPServer(("localhost", 8765), _H).handle_request, daemon=True).start()
    import webbrowser; webbrowser.open(url)
    print("Consentement ouvert dans le navigateur. URL si besoin :\n", url)
    for _ in range(120):
        if "code" in _hold: break
        time.sleep(1)
    if "code" not in _hold:
        raise SystemExit("Pas de code reçu (timeout).")
    form = {"grant_type": "authorization_code", "code": _hold["code"], "redirect_uri": REDIRECT,
            "client_id": CLIENT_ID, "code_verifier": verifier}
    if CLIENT_SECRET:
        form["client_secret"] = CLIENT_SECRET
    req = urllib.request.Request(BASE + "/token", data=urllib.parse.urlencode(form).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    tok = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    access = tok["access_token"]
    print(f"\n[OK] Token obtenu via TON client ({CLIENT_ID[:8]}…). Appel d'OrbiAds…")

    async def call():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(BASE, headers={"Authorization": f"Bearer {access}"}) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("check_credentials", {})
                for c in res.content:
                    print("[OrbiAds] check_credentials ->", getattr(c, "text", c))
    asyncio.run(call())


if __name__ == "__main__":
    main()
