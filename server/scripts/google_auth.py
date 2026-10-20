"""Ottiene il refresh token Google (da eseguire UNA volta sul tuo PC).

    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python scripts/google_auth.py

Prerequisito: nel client OAuth (tipo "Desktop app") nessun redirect da configurare;
con un client "Web" aggiungi http://localhost:8765/ tra gli URI di reindirizzamento.
Poi imposta il token stampato come GOOGLE_REFRESH_TOKEN su Render.
"""
import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.google import SCOPES, TOKEN_URL  # noqa: E402

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/"
cid, secret = os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"]
result: dict = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        result["code"] = q.get("code", [""])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write("Fatto, puoi chiudere questa scheda.".encode())

    def log_message(self, *a):
        pass


url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
    {
        "client_id": cid,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
)
print("Apro il browser per l'autorizzazione...")
webbrowser.open(url)
HTTPServer(("localhost", PORT), Handler).handle_request()
r = httpx.post(
    TOKEN_URL,
    data={"code": result["code"], "client_id": cid, "client_secret": secret, "redirect_uri": REDIRECT, "grant_type": "authorization_code"},
)
r.raise_for_status()
print("\nGOOGLE_REFRESH_TOKEN =", r.json()["refresh_token"])
