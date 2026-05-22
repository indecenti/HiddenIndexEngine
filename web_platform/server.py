"""
web_platform/server.py

Portale HiddenEngine: vetrina pubblica dei giochi + Back Office (BO) con login
per caricare i giochi in drag & drop (.zip del build esportato).

Solo standard library (nessuna dipendenza esterna). Vedi PLATFORM_DESIGN.md.

Avvio:  python web_platform/server.py [--port 8800]
"""

from __future__ import annotations

import os
import io
import sys
import json
import time
import hmac
import base64
import hashlib
import secrets
import zipfile
import tempfile
import shutil
import argparse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
PUBLIC = BASE / "public"
GAMES = BASE / "games"
CONFIG_PATH = BASE / "config.json"
CATALOG_PATH = BASE / "catalog.json"
SESSION_TTL = 8 * 3600  # 8 ore
MAX_UPLOAD = 600 * 1024 * 1024  # 600 MB

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".ico": "image/x-icon",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".webmanifest": "application/manifest+json", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
}


# ── Config & credenziali ──────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Primo avvio: genera credenziali di default e stampale.
    password = secrets.token_urlsafe(9)
    salt = secrets.token_hex(16)
    cfg = {
        "user": "admin",
        "salt": salt,
        "pass_hash": _hash_pw(password, salt),
        "secret": secrets.token_hex(32),
    }
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("=" * 64)
    print(" PRIMO AVVIO — credenziali Back Office generate:")
    print(f"   utente:   admin")
    print(f"   password: {password}")
    print(f" (salvate in {CONFIG_PATH}; cambiale per la produzione)")
    print("=" * 64)
    return cfg


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()


# ── Sessione (cookie firmato HMAC) ──────────────────────────────────────────
def make_token(cfg: dict) -> str:
    payload = f"{cfg['user']}:{int(time.time()) + SESSION_TTL}"
    sig = hmac.new(cfg["secret"].encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + sig


def check_token(cfg: dict, token: str) -> bool:
    try:
        b64, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
        expected = hmac.new(cfg["secret"].encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        _user, exp = payload.split(":", 1)
        return int(exp) > int(time.time())
    except Exception:
        return False


# ── Catalogo ────────────────────────────────────────────────────────────────
def rebuild_catalog() -> dict:
    games = []
    if GAMES.exists():
        for d in sorted(GAMES.iterdir()):
            gj = d / "game.json"
            if d.is_dir() and gj.exists():
                try:
                    g = json.loads(gj.read_text(encoding="utf-8"))
                except Exception:
                    continue
                gid = g.get("id", d.name)
                prefix = f"games/{d.name}/"
                games.append({
                    "id": gid,
                    "title": g.get("title", gid),
                    "description": g.get("description", ""),
                    "version": g.get("version", ""),
                    "languages": g.get("languages", []),
                    "theme_color": g.get("theme_color", "#1b2b4d"),
                    "icon": (prefix + g["icon"]) if g.get("icon") else "",
                    "og_image": (prefix + g["og_image"]) if g.get("og_image") else "",
                    "url": prefix + g.get("url", ""),
                    "built_at": g.get("built_at", ""),
                })
    catalog = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "games": games}
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def install_game_from_zip(zip_bytes: bytes) -> dict:
    """Scompatta lo zip di un gioco esportato e lo installa in games/<id>/."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        zpath = tmp / "upload.zip"
        zpath.write_bytes(zip_bytes)
        extract = tmp / "x"
        extract.mkdir()
        with zipfile.ZipFile(zpath) as zf:
            # Protezione zip-slip: nessun path assoluto o '..'
            for name in zf.namelist():
                p = (extract / name).resolve()
                if not str(p).startswith(str(extract.resolve())):
                    raise ValueError("Zip non sicuro (path traversal)")
            zf.extractall(extract)
        # Trova la cartella che contiene game.json (root o un livello sotto)
        game_root = None
        if (extract / "game.json").exists():
            game_root = extract
        else:
            for sub in extract.iterdir():
                if sub.is_dir() and (sub / "game.json").exists():
                    game_root = sub
                    break
        if not game_root:
            raise ValueError("game.json non trovato nello zip (non e' un build esportato valido)")
        meta = json.loads((game_root / "game.json").read_text(encoding="utf-8"))
        gid = meta.get("id")
        if not gid:
            raise ValueError("game.json senza 'id'")
        dest = GAMES / gid
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(game_root), str(dest))
        rebuild_catalog()
        return {"id": gid, "title": meta.get("title", gid), "version": meta.get("version", "")}


# ── HTTP handler ──────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    cfg = {}

    def log_message(self, *a):  # silenzia il log verboso di default
        pass

    # -- utilita' --
    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj, headers=None):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", headers)

    def _cookie(self) -> str:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "sid":
                    return v
        return ""

    def _authed(self) -> bool:
        return check_token(self.cfg, self._cookie())

    def _serve_file(self, path: Path):
        if not path.is_file():
            return self._send(404, "Not found")
        ctype = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self._send(200, data, ctype, {"Cache-Control": "no-cache"})

    def _safe(self, root: Path, rel: str) -> Path | None:
        p = (root / rel.lstrip("/")).resolve()
        if str(p).startswith(str(root.resolve())):
            return p
        return None

    # -- GET --
    def do_GET(self):
        self._route("GET")

    def do_HEAD(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        path = urlparse(self.path).path
        if method == "GET":
            if path == "/" or path == "/index.html":
                return self._serve_file(PUBLIC / "index.html")
            if path == "/admin" or path == "/admin.html":
                return self._serve_file(PUBLIC / "admin.html")
            if path == "/catalog.json":
                if not CATALOG_PATH.exists():
                    rebuild_catalog()
                return self._serve_file(CATALOG_PATH)
            if path == "/api/me":
                return self._json(200, {"authed": self._authed()})
            if path.startswith("/games/"):
                p = self._safe(GAMES, path[len("/games/"):])
                if p and p.is_dir():
                    p = p / "index.html"
                return self._serve_file(p) if p else self._send(404, "Not found")
            # static dalla cartella public/
            p = self._safe(PUBLIC, path)
            if p and p.is_file():
                return self._serve_file(p)
            return self._send(404, "Not found")

        if method == "POST":
            if path == "/api/login":
                return self._login()
            if path == "/api/logout":
                return self._json(200, {"ok": True}, {"Set-Cookie": "sid=; Path=/; Max-Age=0"})
            if path == "/api/upload":
                return self._upload()
            if path == "/api/delete":
                return self._delete()
            return self._send(404, "Not found")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_UPLOAD:
            raise ValueError("Upload troppo grande")
        return self.rfile.read(n) if n else b""

    def _login(self):
        try:
            data = json.loads(self._body() or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        user = data.get("user", "")
        pw = data.get("pass", "")
        if user == self.cfg["user"] and hmac.compare_digest(_hash_pw(pw, self.cfg["salt"]), self.cfg["pass_hash"]):
            token = make_token(self.cfg)
            cookie = f"sid={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Lax"
            return self._json(200, {"ok": True}, {"Set-Cookie": cookie})
        return self._json(401, {"error": "Credenziali non valide"})

    def _upload(self):
        if not self._authed():
            return self._json(401, {"error": "Non autorizzato"})
        try:
            data = self._body()
            info = install_game_from_zip(data)
            return self._json(200, {"ok": True, "game": info})
        except Exception as e:
            return self._json(400, {"error": str(e)})

    def _delete(self):
        if not self._authed():
            return self._json(401, {"error": "Non autorizzato"})
        try:
            data = json.loads(self._body() or b"{}")
            gid = data.get("id", "")
            p = self._safe(GAMES, gid)
            if p and p.is_dir():
                shutil.rmtree(p)
                rebuild_catalog()
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "Gioco non trovato"})
        except Exception as e:
            return self._json(400, {"error": str(e)})


def main():
    ap = argparse.ArgumentParser(description="Portale HiddenEngine (vetrina + Back Office).")
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    GAMES.mkdir(parents=True, exist_ok=True)
    Handler.cfg = load_config()
    rebuild_catalog()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Portale HiddenEngine su http://{args.host}:{args.port}  (BO: /admin)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArresto.")
        srv.shutdown()


if __name__ == "__main__":
    main()
