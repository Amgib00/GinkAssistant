"""
The FastAPI backend -- this didn't exist anywhere in the Toga rebuild
until now. The original __main__.py defined /send-otp and /verify-otp
directly on `app` (confirmed as the real, live routes, separate from the
dead-code router in auth_service.py) and started it with
`uvicorn.run(app, host="127.0.0.1", port=8000)` in a background thread
before showing the login screen. Since that file is gone along with the
PySide6 code, nothing was left to start a server at all -- hence
"couldn't reach the server".

This reproduces that route pair, matching the real behavior: a 6-digit
OTP with a 5-minute TTL in a thread-safe in-memory store, and a JWT on
successful verification (PyJWT, HS256).

One deliberate difference from the original: if GMAIL_USER/
GMAIL_APP_PASSWORD aren't set, this prints the OTP to the console instead
of failing the request outright, so login works immediately for local
testing without needing real email credentials configured first. Set
those two environment variables whenever you want it to actually email
the code instead.

Hardened per request to make this "bulletproof" -- concretely, none of
the following existed before:
  - Server-side email format validation. The client (ui/login_screen.py)
    already validates, but this server binds to 127.0.0.1 and is
    reachable by *any* local process, not just the Toga UI -- trusting
    the client alone isn't real validation.
  - A per-email resend cooldown on /send-otp (429 if asked again too
    soon), matching the client's own 30s cooldown -- that client-side
    one is trivially bypassed by anyone calling this API directly, so
    the real enforcement has to live here. This also protects against
    hammering Gmail's SMTP fast enough to get the sending account
    flagged.
  - A failed-attempt lockout on /verify-otp. Before this, a 6-digit OTP
    had *zero* rate limiting against guessing -- over localhost, with no
    throttling at all, all million combinations are crackable well
    within the 5-minute TTL by a simple script. Matches the original
    PySide6 GinkAssistantLogin's own self.max_attempts = 3 concept,
    enforced server-side now instead of just in the client UI (which,
    again, anyone hitting this API directly would simply not run).
  - SECRET_KEY no longer defaults to a hardcoded, publicly-readable
    placeholder string if GINK_SECRET_KEY isn't set. That default was a
    real risk: anyone reading this source could forge valid session
    tokens for any deployment that forgot to set the env var. Now, with
    no env var set, a strong random secret is generated once and
    persisted to disk (via configure_secret_path(), called from app.py
    with a real app.paths-derived location -- this module has no Toga
    App instance of its own to resolve one itself, consistent with how
    services/paths.py's docstring explains why __file__/cwd-relative
    paths aren't reliable once packaged) so it survives restarts without
    invalidating every session, but is never shared or predictable.
  - Expired, never-verified OTP entries are now swept out periodically
    instead of sitting in memory forever.
"""

import os
import random
import re
import secrets
import smtplib
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException

ALGORITHM = "HS256"
OTP_TTL_SECONDS = 300
RESEND_COOLDOWN_SECONDS = 30
MAX_VERIFY_ATTEMPTS = 5
MAX_EMAIL_LENGTH = 254  # RFC 5321
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Gink Assistant Backend")

_otp_store: dict[str, dict] = {}
_otp_lock = threading.Lock()

_secret_key_path: Optional[Path] = None
_secret_key_cache: Optional[str] = None
_secret_key_lock = threading.Lock()


def configure_secret_path(path: Path):
    """Call this from app.py, before the server starts accepting
    requests, with a real writable directory (data_dir(app) / "secret.key")
    -- see the module docstring for why this can't resolve its own path."""
    global _secret_key_path
    _secret_key_path = path


def _get_secret_key() -> str:
    global _secret_key_cache
    env_key = os.environ.get("GINK_SECRET_KEY", "").strip()
    if env_key:
        return env_key

    with _secret_key_lock:
        if _secret_key_cache:
            return _secret_key_cache
        if _secret_key_path:
            try:
                if _secret_key_path.exists():
                    _secret_key_cache = _secret_key_path.read_text().strip()
                    if _secret_key_cache:
                        return _secret_key_cache
            except Exception:
                pass
            generated = secrets.token_hex(32)
            try:
                _secret_key_path.parent.mkdir(parents=True, exist_ok=True)
                _secret_key_path.write_text(generated)
            except Exception:
                pass  # still usable this run, just won't survive a restart
            _secret_key_cache = generated
            return generated

        # No configure_secret_path() call and no env var -- a fresh
        # random secret per process start is still strictly safer than a
        # shared hardcoded default, just won't survive a restart.
        _secret_key_cache = secrets.token_hex(32)
        return _secret_key_cache


def _create_session_token(email: str) -> str:
    payload = {
        "sub": email,
        "iat": time.time(),
        "exp": time.time() + 86400,
        "iss": "gink_assistant",
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def _dispatch_otp(email: str, otp: str) -> None:
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = (
        os.environ.get("GMAIL_APP_PASSWORD")
        or os.environ.get("GMAIL_PASSWORD")
        or os.environ.get("GMAIL_PASS")
        or ""
    ).replace(" ", "").strip()

    if not gmail_user or not gmail_pass:
        print(f"[Gink] No email configured -- your OTP for {email} is: {otp}")
        return

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = email
    msg["Subject"] = "Gink Assistant - Your Security Code"
    msg.attach(MIMEText(f"Your Gink Assistant code is: {otp}\n\nExpires in 5 minutes.", "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.send_message(msg)


def _sweep_expired_locked():
    """Called with _otp_lock already held. Drops entries that expired
    and were never verified, so this dict doesn't grow unbounded over a
    long-running backend."""
    now = time.time()
    dead = [e for e, entry in _otp_store.items() if now > entry["expiry"]]
    for e in dead:
        del _otp_store[e]


def _validate_email(email: str):
    email = (email or "").strip()
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="That doesn't look like a valid email address.")
    return email


@app.get("/health")
async def health():
    """Lets the app's "Test connection" button (services/server_config.py)
    check this server is reachable without sending anyone an email."""
    return {"status": "ok", "service": "gink-backend"}


@app.post("/send-otp")
def send_otp(email: str):
    email = _validate_email(email)
    otp = str(random.randint(100000, 999999))

    with _otp_lock:
        _sweep_expired_locked()
        existing = _otp_store.get(email)
        if existing and (time.time() - existing["sent_at"]) < RESEND_COOLDOWN_SECONDS:
            wait = int(RESEND_COOLDOWN_SECONDS - (time.time() - existing["sent_at"]))
            raise HTTPException(status_code=429, detail=f"Wait {wait}s before requesting another code.")
        _otp_store[email] = {
            "otp": otp, "expiry": time.time() + OTP_TTL_SECONDS,
            "sent_at": time.time(), "failed_attempts": 0,
        }

    try:
        _dispatch_otp(email, otp)
    except Exception as exc:
        print(f"[Gink] Email dispatch failed, falling back to console -- your OTP for {email} is: {otp} ({exc})")
    return {"status": "success"}


@app.post("/verify-otp")
def verify_otp(email: str, otp: str):
    email = _validate_email(email)
    otp = (otp or "").strip()

    with _otp_lock:
        entry = _otp_store.get(email)
        if not entry:
            raise HTTPException(status_code=401, detail="No code was requested for this email.")
        if time.time() > entry["expiry"]:
            del _otp_store[email]
            raise HTTPException(status_code=401, detail="That code has expired.")
        if entry["otp"] != otp:
            entry["failed_attempts"] += 1
            if entry["failed_attempts"] >= MAX_VERIFY_ATTEMPTS:
                del _otp_store[email]
                raise HTTPException(status_code=401, detail="Too many incorrect attempts -- request a new code.")
            remaining = MAX_VERIFY_ATTEMPTS - entry["failed_attempts"]
            raise HTTPException(status_code=401, detail=f"Incorrect code. {remaining} attempt(s) left.")
        del _otp_store[email]

    return {"token": _create_session_token(email), "email": email}

# =====================================================================
# Accounts: password sign-up/login, email verification, password reset,
# and sign-in with Google / Apple / Microsoft / GitHub / company SSO.
#
# Everything stays in this one file so deploy/Dockerfile can still copy
# just backend_server.py. Users live in a small SQLite file next to the
# secret key (or GINK_DB_PATH). Passwords are hashed with scrypt (stdlib).
#
# Social sign-in uses the normal web OAuth "authorization code" flow:
#   app opens  {server}/auth/<provider>/start?state=<random>  in the browser
#   provider -> {server}/auth/<provider>/callback  (we exchange the code)
#   app polls  {server}/auth/poll?state=<random>  until the token is ready
# A provider only appears in the app once its keys are set on the server
# (see deploy/README.md, "Sign in with Google, Apple, ...").
# =====================================================================
import base64
import hashlib
import hmac
import html as _html
import json as _json
import sqlite3
import urllib.parse

from fastapi import Body, Request
from fastapi.responses import HTMLResponse, RedirectResponse

MIN_PASSWORD_LENGTH = 8
LOGIN_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_FAILURES = 6
OAUTH_STATE_TTL = 10 * 60

_db_lock = threading.Lock()
_login_failures: dict[str, list] = {}
_pending_signups: dict[str, dict] = {}     # email -> {name, pw_hash, code, expiry, attempts}
_reset_codes: dict[str, dict] = {}         # email -> {code, expiry, attempts}
_oauth_states: dict[str, dict] = {}        # state -> {provider, created, result}


def _db_path() -> Path:
    env = os.environ.get("GINK_DB_PATH", "").strip()
    if env:
        return Path(env)
    if _secret_key_path:
        return _secret_key_path.parent / "users.db"
    return Path("users.db")


def _db():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " email TEXT PRIMARY KEY, name TEXT DEFAULT '', pw_hash TEXT DEFAULT '',"
        " providers TEXT DEFAULT '', created REAL)"
    )
    return con


def _get_user(email: str) -> Optional[dict]:
    with _db_lock:
        con = _db()
        try:
            row = con.execute("SELECT email, name, pw_hash, providers FROM users WHERE email = ?",
                              (email,)).fetchone()
        finally:
            con.close()
    if not row:
        return None
    return {"email": row[0], "name": row[1], "pw_hash": row[2], "providers": row[3]}


def _upsert_user(email: str, name: str = "", pw_hash: Optional[str] = None, provider: Optional[str] = None):
    with _db_lock:
        con = _db()
        try:
            row = con.execute("SELECT name, pw_hash, providers FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                con.execute("INSERT INTO users (email, name, pw_hash, providers, created) VALUES (?,?,?,?,?)",
                            (email, name or "", pw_hash or "", provider or "", time.time()))
            else:
                providers = set(p for p in (row[2] or "").split(",") if p)
                if provider:
                    providers.add(provider)
                con.execute("UPDATE users SET name = ?, pw_hash = ?, providers = ? WHERE email = ?",
                            (name or row[0], pw_hash if pw_hash is not None else row[1],
                             ",".join(sorted(providers)), email))
            con.commit()
        finally:
            con.close()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def _check_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except Exception:
        return False


def _validate_password(password: str) -> str:
    password = password or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if password.isdigit() or password.isalpha():
        raise HTTPException(status_code=422, detail="Mix letters with numbers or symbols.")
    return password


def _token_response(email: str, name: str = "") -> dict:
    payload = {"sub": email, "name": name or "", "iat": time.time(), "exp": time.time() + 30 * 86400,
               "iss": "gink_assistant"}
    return {"token": jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM), "email": email, "name": name or ""}


def _send_code_email(email: str, code: str, subject: str, intro: str):
    """Reuses the OTP mailer; falls back to printing the code."""
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_PASSWORD")
                  or os.environ.get("GMAIL_PASS") or "").replace(" ", "").strip()
    if not gmail_user or not gmail_pass:
        print(f"[Gink] No email configured -- {subject} code for {email}: {code}")
        return
    try:
        msg = MIMEMultipart()
        msg["From"], msg["To"], msg["Subject"] = gmail_user, email, f"Gink Assistant - {subject}"
        msg.attach(MIMEText(f"{intro}\n\nYour code: {code}\n\nIt expires in 10 minutes.", "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
    except Exception as exc:
        print(f"[Gink] Email failed ({exc}) -- {subject} code for {email}: {code}")


def _check_code(store: dict, email: str, code: str) -> dict:
    entry = store.get(email)
    if not entry:
        raise HTTPException(status_code=401, detail="Request a new code first.")
    if time.time() > entry["expiry"]:
        store.pop(email, None)
        raise HTTPException(status_code=401, detail="That code has expired. Request a new one.")
    if not hmac.compare_digest(entry["code"], (code or "").strip()):
        entry["attempts"] += 1
        if entry["attempts"] >= MAX_VERIFY_ATTEMPTS:
            store.pop(email, None)
            raise HTTPException(status_code=401, detail="Too many wrong codes. Request a new one.")
        raise HTTPException(status_code=401, detail=f"Wrong code. {MAX_VERIFY_ATTEMPTS - entry['attempts']} tries left.")
    return store.pop(email)


# ---------------------------------------------------------------- password accounts

@app.post("/auth/register")
def register(data: dict = Body(...)):
    email = _validate_email(data.get("email", "")).lower()
    name = (data.get("name") or "").strip()[:80]
    password = _validate_password(data.get("password", ""))
    existing = _get_user(email)
    if existing and existing["pw_hash"]:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Log in instead.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    with _otp_lock:
        _pending_signups[email] = {"name": name, "pw_hash": _hash_password(password), "code": code,
                                   "expiry": time.time() + 600, "attempts": 0}
    _send_code_email(email, code, "Verify your email", f"Welcome to Gink{', ' + name if name else ''}!")
    return {"status": "code_sent"}


@app.post("/auth/register/verify")
def register_verify(data: dict = Body(...)):
    email = _validate_email(data.get("email", "")).lower()
    time.sleep(0.001)          # new token's iat is strictly after any deletion time
    with _otp_lock:
        entry = _check_code(_pending_signups, email, data.get("code", ""))
    _upsert_user(email, entry["name"], entry["pw_hash"], "password")
    return _token_response(email, entry["name"])


@app.post("/auth/login")
def login(data: dict = Body(...)):
    email = _validate_email(data.get("email", "")).lower()
    now = time.time()
    with _otp_lock:
        recent = [t for t in _login_failures.get(email, []) if now - t < LOGIN_WINDOW_SECONDS]
        _login_failures[email] = recent
        if len(recent) >= MAX_LOGIN_FAILURES:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes or reset your password.")
    user = _get_user(email)
    if not user or not user["pw_hash"] or not _check_password(data.get("password", ""), user["pw_hash"]):
        with _otp_lock:
            _login_failures.setdefault(email, []).append(now)
        if user and not user["pw_hash"] and user["providers"]:
            raise HTTPException(status_code=401, detail=f"This account signs in with {user['providers'].split(',')[0].title()}.")
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    with _otp_lock:
        _login_failures.pop(email, None)
    return _token_response(email, user["name"])


@app.post("/auth/forgot")
def forgot(data: dict = Body(...)):
    email = _validate_email(data.get("email", "")).lower()
    # Same answer whether or not the account exists (no account probing).
    if _get_user(email):
        code = f"{secrets.randbelow(1_000_000):06d}"
        with _otp_lock:
            _reset_codes[email] = {"code": code, "expiry": time.time() + 600, "attempts": 0}
        _send_code_email(email, code, "Reset your password", "Someone asked to reset your Gink password.")
    return {"status": "code_sent"}


@app.post("/auth/reset")
def reset(data: dict = Body(...)):
    email = _validate_email(data.get("email", "")).lower()
    password = _validate_password(data.get("password", ""))
    with _otp_lock:
        _check_code(_reset_codes, email, data.get("code", ""))
        _login_failures.pop(email, None)
    user = _get_user(email) or {"name": ""}
    _upsert_user(email, user["name"], _hash_password(password), "password")
    return _token_response(email, user["name"])


# ---------------------------------------------------------------- social / SSO

def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


PROVIDERS = {
    "google": {
        "label": "Google", "keys": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token", "scope": "openid email profile",
        "extra": {"prompt": "select_account"},
    },
    "apple": {
        "label": "Apple", "keys": ("APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY"),
        "authorize": "https://appleid.apple.com/auth/authorize",
        "token": "https://appleid.apple.com/auth/token", "scope": "name email",
        "extra": {"response_mode": "form_post"},
    },
    "microsoft": {
        "label": "Microsoft", "keys": ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token", "scope": "openid email profile",
        "extra": {"prompt": "select_account"},
    },
    "github": {
        "label": "GitHub", "keys": ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"),
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token", "scope": "read:user user:email",
        "extra": {},
    },
    "sso": {   # any OpenID Connect provider: Okta, Auth0, Azure AD tenant, Keycloak, ...
        "label": _env("SSO_LABEL") or "SSO", "keys": ("SSO_ISSUER", "SSO_CLIENT_ID", "SSO_CLIENT_SECRET"),
        "authorize": None, "token": None, "scope": "openid email profile", "extra": {},
    },
}


def _configured(provider: str) -> bool:
    p = PROVIDERS.get(provider)
    return bool(p) and all(_env(k) for k in p["keys"])


def _client_id(provider: str) -> str:
    return _env(f"{provider.upper()}_CLIENT_ID")


def _client_secret(provider: str) -> str:
    if provider == "apple":
        # Apple wants a short-lived ES256 JWT signed with your .p8 key.
        key = _env("APPLE_PRIVATE_KEY").replace("\\n", "\n")
        now = int(time.time())
        return jwt.encode({"iss": _env("APPLE_TEAM_ID"), "iat": now, "exp": now + 3000,
                           "aud": "https://appleid.apple.com", "sub": _env("APPLE_CLIENT_ID")},
                          key, algorithm="ES256", headers={"kid": _env("APPLE_KEY_ID")})
    return _env(f"{provider.upper()}_CLIENT_SECRET")


def _sso_endpoints() -> tuple:
    import httpx
    issuer = _env("SSO_ISSUER").rstrip("/")
    conf = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10).json()
    return conf["authorization_endpoint"], conf["token_endpoint"]


_LOCAL_HOSTS = ("://localhost", "://127.0.0.1", "://0.0.0.0", "://10.0.2.2", "://[::1]")
_public_url_warned = False


def _request_base(request: Request) -> str:
    """This server's address as the visitor reached it. Behind Render's proxy the connection
    is plain http inside, so the proxy's X-Forwarded-Proto says whether it was https."""
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _public_base(request: Request) -> str:
    """Where sign-in providers and payments send people back. GINK_PUBLIC_URL wins -- unless it
    points at this computer (localhost...) while the request came from the internet: then it
    was copied from a local .env by mistake, and the provider would send people to *their own*
    computer ("sign-in link expired" on localhost). Use the real address and say so in the logs."""
    global _public_url_warned
    configured = _env("GINK_PUBLIC_URL").rstrip("/")
    real = _request_base(request).rstrip("/")
    is_local = lambda u: any(h in u for h in _LOCAL_HOSTS)
    if configured and (not is_local(configured) or is_local(real)):
        return configured
    if configured and not _public_url_warned:
        _public_url_warned = True
        print(f"[Gink] WARNING: GINK_PUBLIC_URL is {configured}, but this server is reached at {real}. "
              f"Using {real}. Set GINK_PUBLIC_URL={real} in your hosting settings.", flush=True)
    return real


def _sweep_states():
    now = time.time()
    for s in [s for s, v in _oauth_states.items() if now - v["created"] > OAUTH_STATE_TTL]:
        _oauth_states.pop(s, None)


@app.get("/auth/providers")
def providers():
    return {name: {"enabled": _configured(name), "label": p["label"]} for name, p in PROVIDERS.items()}


def _register_state(provider: str, state: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{16,128}", state or ""):
        raise HTTPException(status_code=400, detail="Bad state.")
    with _otp_lock:
        _sweep_states()
        existing = _oauth_states.get(state)
        if existing and existing["provider"] != provider:
            raise HTTPException(status_code=409, detail="State already in use.")
        if not existing:
            _oauth_states[state] = {"provider": provider, "created": time.time(), "result": None}


@app.post("/auth/{provider}/begin")
def oauth_begin(provider: str, data: dict = Body(...)):
    """The app registers its sign-in ticket BEFORE opening the browser, so
    its first /auth/poll can never arrive ahead of the browser's /start
    (that race produced a false "Sign-in expired")."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown sign-in provider.")
    if not _configured(provider):
        raise HTTPException(status_code=503, detail=f"{PROVIDERS[provider]['label']} sign-in isn't set up on this server yet.")
    _register_state(provider, data.get("state", ""))
    return {"status": "ok"}


@app.get("/auth/{provider}/start")
def oauth_start(provider: str, state: str, request: Request):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown sign-in provider.")
    if not _configured(provider):
        return HTMLResponse(_result_page(False, f"{PROVIDERS[provider]['label']} sign-in isn't set up on this "
                                                 "server yet."), status_code=503)
    _register_state(provider, state)        # usually already registered by /begin
    p = PROVIDERS[provider]
    authorize = _sso_endpoints()[0] if provider == "sso" else p["authorize"]
    params = {"client_id": _client_id(provider), "redirect_uri": f"{_public_base(request)}/auth/{provider}/callback",
              "response_type": "code", "scope": p["scope"], "state": state, **p["extra"]}
    return RedirectResponse(authorize + "?" + urllib.parse.urlencode(params))


def _unverified_claims(id_token: str) -> dict:
    # The ID token comes straight from the provider's token endpoint over
    # TLS in exchange for our client secret, which OpenID Connect allows
    # as validation of its origin (OIDC Core 3.1.3.7, item 6).
    return jwt.decode(id_token, options={"verify_signature": False})


def _identity_from_code(provider: str, code: str, redirect_uri: str, apple_user: str = "") -> tuple:
    import httpx
    p = PROVIDERS[provider]
    token_url = _sso_endpoints()[1] if provider == "sso" else p["token"]
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": _client_id(provider), "client_secret": _client_secret(provider)}
    r = httpx.post(token_url, data=data, headers={"Accept": "application/json"}, timeout=15)
    tok = r.json()
    if r.status_code != 200 or ("id_token" not in tok and "access_token" not in tok):
        raise ValueError(tok.get("error_description") or tok.get("error") or "token exchange failed")
    if provider == "github":
        h = {"Authorization": f"Bearer {tok['access_token']}", "Accept": "application/vnd.github+json"}
        user = httpx.get("https://api.github.com/user", headers=h, timeout=15).json()
        emails = httpx.get("https://api.github.com/user/emails", headers=h, timeout=15).json()
        primary = next((e["email"] for e in emails if e.get("primary") and e.get("verified")), None)
        if not primary:
            raise ValueError("Your GitHub account has no verified email.")
        return primary.lower(), user.get("name") or user.get("login") or ""
    claims = _unverified_claims(tok["id_token"])
    aud = claims.get("aud")
    if _client_id(provider) not in (aud if isinstance(aud, list) else [aud]):
        raise ValueError("ID token was issued for a different app.")
    if claims.get("exp", 0) < time.time():
        raise ValueError("ID token expired.")
    email = (claims.get("email") or claims.get("preferred_username") or "").lower()
    if not email or claims.get("email_verified") in (False, "false"):
        raise ValueError("Your account didn't share a verified email address.")
    name = claims.get("name") or ""
    if provider == "apple" and apple_user:      # Apple sends the name only the first time
        try:
            n = _json.loads(apple_user).get("name", {})
            name = " ".join(x for x in (n.get("firstName"), n.get("lastName")) if x)
        except Exception:
            pass
    return email, name


def _result_page(ok: bool, message: str, title: Optional[str] = None) -> str:
    color = "#3F8212" if ok else "#C93B32"
    icon = "&#10003;" if ok else "!"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Gink</title></head><body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#F1F3EE;color:#1C211D">
<div style="background:#fff;padding:36px 40px;border-radius:24px;text-align:center;max-width:360px;
box-shadow:0 20px 50px rgba(28,33,29,.12)"><div style="width:56px;height:56px;border-radius:50%;margin:0 auto 14px;
background:{color};color:#fff;font-size:28px;line-height:56px">{icon}</div>
<h2 style="margin:0 0 8px">{_html.escape(quote=False, s=title or ('You are signed in' if ok else 'Sign-in failed'))}</h2>
<p style="color:#6E756D;margin:0">{_html.escape(message)}</p></div></body></html>"""


async def _oauth_callback(provider: str, request: Request):
    form = {}
    if request.method == "POST":
        form = dict(await request.form())
    params = {**dict(request.query_params), **form}
    state = params.get("state", "")
    with _otp_lock:
        entry = _oauth_states.get(state)
    if not entry or entry["provider"] != provider:
        return HTMLResponse(_result_page(False, "This sign-in link expired. Start again from Gink."), status_code=400)
    if params.get("error"):
        entry["result"] = {"error": params.get("error_description") or "Sign-in was cancelled."}
        return HTMLResponse(_result_page(False, "Sign-in was cancelled. You can close this tab."))
    try:
        import asyncio as _asyncio
        email, name = await _asyncio.get_event_loop().run_in_executor(
            None, _identity_from_code, provider, params.get("code", ""),
            f"{_public_base(request)}/auth/{provider}/callback", params.get("user", ""))
        existing = _get_user(email)
        _upsert_user(email, name or (existing or {}).get("name", ""), None, provider)
        entry["result"] = _token_response(email, name or (existing or {}).get("name", ""))
        return HTMLResponse(_result_page(True, "Go back to Gink \u2014 you can close this tab."))
    except Exception as exc:
        entry["result"] = {"error": f"{PROVIDERS[provider]['label']} sign-in failed: {exc}"}
        return HTMLResponse(_result_page(False, str(exc)), status_code=400)


@app.get("/auth/{provider}/callback")
async def oauth_callback_get(provider: str, request: Request):
    return await _oauth_callback(provider, request)


@app.post("/auth/{provider}/callback")
async def oauth_callback_post(provider: str, request: Request):   # Apple uses form_post
    return await _oauth_callback(provider, request)


@app.get("/auth/poll")
def oauth_poll(state: str):
    with _otp_lock:
        entry = _oauth_states.get(state)
        if not entry:
            raise HTTPException(status_code=404, detail="Sign-in expired. Try again.")
        if entry["result"] is None:
            return {"status": "pending"}
        _oauth_states.pop(state, None)
    result = entry["result"]
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


# =====================================================================
# Sync: chats, Workspace items and memories, per account.
#
#   POST /sync   Authorization: Bearer <session token>
#   {"since": <server time from last sync>, "push": {"chats": [...], "items": [...], "memories": [...]}}
#   -> {"now": <server time>, "changes": {"chats": [...], ...}}
#
# Each doc is {"id", "updated", "deleted", "payload"}. The newest
# "updated" wins; deletions are kept as tombstones so they reach every
# device. Stored in the same SQLite file as the accounts.
# =====================================================================
SYNC_KINDS_SERVER = ("chats", "items", "memories", "profile")
MAX_SYNC_DOCS = 2000
MAX_DOC_BYTES = 2_000_000


def _sync_db():
    con = _db()
    con.execute(
        "CREATE TABLE IF NOT EXISTS sync_docs ("
        " email TEXT NOT NULL, kind TEXT NOT NULL, doc_id TEXT NOT NULL, payload TEXT NOT NULL,"
        " updated REAL NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, server_ts REAL NOT NULL,"
        " PRIMARY KEY (email, kind, doc_id))"
    )
    con.execute("CREATE INDEX IF NOT EXISTS sync_docs_ts ON sync_docs (email, server_ts)")
    return con


def _email_from_auth(request: Request) -> str:
    api_email = getattr(request.state, "gink_api_email", None)      # set only after an API key was verified
    if api_email:
        return api_email
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in again to sync.")
    try:
        claims = jwt.decode(auth[7:].strip(), _get_secret_key(), algorithms=[ALGORITHM], issuer="gink_assistant")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again to sync.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Sign in again to sync.")
    email = (claims.get("sub") or "").lower()
    # tokens issued before the account was deleted stop working immediately
    with _db_lock:
        con = _db()
        try:
            con.execute("CREATE TABLE IF NOT EXISTS deleted_accounts (email TEXT PRIMARY KEY, at REAL NOT NULL)")
            row = con.execute("SELECT at FROM deleted_accounts WHERE email=?", (email,)).fetchone()
        finally:
            con.close()
    if row and float(claims.get("iat") or 0) <= row[0]:
        raise HTTPException(status_code=401, detail="This account was deleted.")
    return email


@app.post("/sync")
def sync(request: Request, data: dict = Body(...)):
    email = _email_from_auth(request)
    since = float(data.get("since") or 0)
    push = data.get("push") or {}
    changes = {k: [] for k in SYNC_KINDS_SERVER}
    with _db_lock:
        con = _sync_db()
        try:
            now = time.time()
            for kind in SYNC_KINDS_SERVER:
                for doc in (push.get(kind) or [])[:MAX_SYNC_DOCS]:
                    doc_id, updated = str(doc.get("id") or "")[:200], float(doc.get("updated") or 0)
                    payload = _json.dumps(doc.get("payload") or {})
                    if not doc_id or len(payload) > MAX_DOC_BYTES:
                        continue
                    row = con.execute("SELECT updated FROM sync_docs WHERE email=? AND kind=? AND doc_id=?",
                                      (email, kind, doc_id)).fetchone()
                    if row and row[0] >= updated:
                        continue
                    con.execute("INSERT OR REPLACE INTO sync_docs (email, kind, doc_id, payload, updated, deleted,"
                                " server_ts) VALUES (?,?,?,?,?,?,?)",
                                (email, kind, doc_id, "{}" if doc.get("deleted") else payload, updated,
                                 int(bool(doc.get("deleted"))), now))
            con.commit()
            rows = con.execute("SELECT kind, doc_id, payload, updated, deleted FROM sync_docs"
                               " WHERE email=? AND server_ts > ? ORDER BY server_ts LIMIT ?",
                               (email, since, MAX_SYNC_DOCS * 3)).fetchall()
        finally:
            con.close()
    for kind, doc_id, payload, updated, deleted in rows:
        if kind in changes:
            changes[kind].append({"id": doc_id, "updated": updated, "deleted": bool(deleted),
                                  "payload": _json.loads(payload)})
    return {"now": now, "changes": changes}


# =====================================================================
# Billing: Gink Pro, paid with the right method for the user's country.
#
#   GET  /billing/options   (auth; ?tz=&locale=&country=)  country, prices, methods
#   POST /billing/country   (auth) {"country": "SN"}        remember the user's choice
#   POST /billing/checkout  (auth) {"plan", "method", "country"} -> {"payment_url", "reference"}
#   GET  /billing/status    (auth; ?reference=)             plan status (+ re-checks a pending payment)
#   GET|POST /billing/notify/cinetpay                       CinetPay notification
#   POST /billing/webhook/paystack                          Paystack webhook (signed)
#   GET  /billing/return                                    page shown after paying
#
# Rules followed for real money:
#   * a payment is only credited after the server asks the PROVIDER directly
#     (never on the app's word, never on the notification alone), and only if
#     the amount and currency match what this server asked for;
#   * crediting is idempotent -- notifications can arrive many times;
#   * "waiting for the customer to approve on their phone" stays pending.
# Mobile money has no automatic renewal, so Pro is sold as prepaid periods
# (1 / 3 / 12 months) that extend from the current end date.
# =====================================================================
try:
    from . import billing_catalog as catalog
except ImportError:                       # deployed as standalone files (deploy/Dockerfile)
    import billing_catalog as catalog

PLAN_DAYS = {"pro_1m": 30, "pro_3m": 91, "pro_12m": 365}
FRANCOPHONE = {"SN", "CI", "ML", "BF", "BJ", "TG", "NE", "GW", "CM", "GA", "CG", "TD", "CF", "GQ", "GN", "CD", "MG", "FR"}


def _billing_db():
    con = _db()
    cols = {r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()}
    if "country" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN country TEXT DEFAULT ''")
    if "pro_until" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN pro_until REAL DEFAULT 0")
    con.execute(
        "CREATE TABLE IF NOT EXISTS payments ("
        " reference TEXT PRIMARY KEY, email TEXT NOT NULL, provider TEXT NOT NULL, plan TEXT NOT NULL,"
        " method TEXT, amount REAL NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL,"
        " created REAL NOT NULL, updated REAL NOT NULL, credited INTEGER NOT NULL DEFAULT 0, detail TEXT DEFAULT '')"
    )
    return con


def _billing_user(email: str) -> dict:
    with _db_lock:
        con = _billing_db()
        try:
            row = con.execute("SELECT country, pro_until, name FROM users WHERE email=?", (email,)).fetchone()
            if row is None:
                con.execute("INSERT INTO users (email, created) VALUES (?, ?)", (email, time.time()))
                con.commit()
                row = ("", 0, "")
        finally:
            con.close()
    return {"country": row[0] or "", "pro_until": row[1] or 0, "name": row[2] or ""}


def _plan_status(email: str) -> dict:
    u = _billing_user(email)
    active = u["pro_until"] > time.time()
    return {"plan": "pro" if active else "free", "pro_until": u["pro_until"] if active else 0}


@app.get("/billing/options")
def billing_options(request: Request, tz: str = "", locale: str = "", country: str = ""):
    email = _email_from_auth(request)
    user = _billing_user(email)
    code, source = catalog.detect_country(chosen=country or user["country"],
                                          cdn_header=request.headers.get("cf-ipcountry", ""),
                                          tz=tz, locale=locale)
    opts = catalog.options_for(code)
    opts.update({"source": source, "status": _plan_status(email),
                 "countries": [{"code": c, "name": n} for c, n in catalog.all_countries()]})
    return opts


@app.post("/billing/country")
def billing_country(request: Request, data: dict = Body(...)):
    email = _email_from_auth(request)
    code = (data.get("country") or "").upper()
    if code and (len(code) != 2 or not code.isalpha()):
        raise HTTPException(status_code=422, detail="Use a two-letter country code.")
    _billing_user(email)
    with _db_lock:
        con = _billing_db()
        try:
            con.execute("UPDATE users SET country=? WHERE email=?", (code, email))
            con.commit()
        finally:
            con.close()
    return catalog.options_for(code)


def _http_post_json(url, payload, headers=None):
    import httpx
    r = httpx.post(url, json=payload, headers={"User-Agent": "GinkServer/1.0", **(headers or {})}, timeout=20)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def _http_get_json(url, headers=None):
    import httpx
    r = httpx.get(url, headers={"User-Agent": "GinkServer/1.0", **(headers or {})}, timeout=20)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def _start_cinetpay(ref, email, name, plan, method, amount, currency, country, base):
    channels = {"card": "CREDIT_CARD"}.get(method, "MOBILE_MONEY")
    first, _, last = (name or email.split("@")[0]).partition(" ")
    payload = {
        "apikey": _env("CINETPAY_API_KEY"), "site_id": _env("CINETPAY_SITE_ID"),
        "transaction_id": ref, "amount": int(amount), "currency": currency,
        "description": f"Gink Pro {plan.replace('pro_', '').replace('m', ' month')}",   # no special characters
        "notify_url": f"{base}/billing/notify/cinetpay", "return_url": f"{base}/billing/return?ref={ref}",
        "channels": channels, "lang": "fr" if country in FRANCOPHONE else "en", "metadata": ref,
        "customer_id": email, "customer_email": email,
        "customer_name": (last or first)[:40], "customer_surname": first[:40],
    }
    if channels == "CREDIT_CARD":
        # required by CinetPay for card; the card form itself collects the real billing details
        payload.update({"customer_phone_number": "", "customer_address": "-", "customer_city": "-",
                        "customer_country": country or "SN", "customer_state": country or "SN",
                        "customer_zip_code": "00000"})
    status, data = _http_post_json("https://api-checkout.cinetpay.com/v2/payment", payload)
    url = (data.get("data") or {}).get("payment_url")
    if status != 200 or str(data.get("code")) != "201" or not url:
        raise HTTPException(status_code=502, detail=f"CinetPay couldn't start the payment ({data.get('description') or data.get('message') or status}).")
    return url


def _check_cinetpay(ref):
    """-> ("success"|"failed"|"pending", amount, currency)"""
    status, data = _http_post_json("https://api-checkout.cinetpay.com/v2/payment/check",
                                   {"apikey": _env("CINETPAY_API_KEY"), "site_id": _env("CINETPAY_SITE_ID"),
                                    "transaction_id": ref})
    d = data.get("data") or {}
    st = (d.get("status") or "").upper()
    if str(data.get("code")) == "00" and st == "ACCEPTED":
        return "success", float(d.get("amount") or 0), (d.get("currency") or "").upper()
    if st == "REFUSED":
        return "failed", 0, ""
    return "pending", 0, ""        # includes WAITING_FOR_CUSTOMER (approve on the phone)


PAYSTACK_CHANNELS = {"card": ["card"], "mobile_money": ["mobile_money"], "bank_transfer": ["bank_transfer"],
                     "ussd": ["ussd"], "mpesa": ["mobile_money"], "mtn_momo": ["mobile_money"],
                     "telecel_cash": ["mobile_money"], "at_money": ["mobile_money"]}


def _start_paystack(ref, email, name, plan, method, amount, currency, country, base):
    status, data = _http_post_json(
        "https://api.paystack.co/transaction/initialize",
        {"email": email, "amount": int(round(amount * 100)), "currency": currency, "reference": ref,
         "callback_url": f"{base}/billing/return?ref={ref}", "metadata": {"plan": plan, "gink_ref": ref},
         "channels": PAYSTACK_CHANNELS.get(method, ["card"])},
        headers={"Authorization": f"Bearer {_env('PAYSTACK_SECRET_KEY')}"})
    url = (data.get("data") or {}).get("authorization_url")
    if status != 200 or not data.get("status") or not url:
        raise HTTPException(status_code=502, detail=f"Paystack couldn't start the payment ({data.get('message') or status}).")
    return url


def _check_paystack(ref):
    status, data = _http_get_json(f"https://api.paystack.co/transaction/verify/{urllib.parse.quote(ref)}",
                                  headers={"Authorization": f"Bearer {_env('PAYSTACK_SECRET_KEY')}"})
    d = data.get("data") or {}
    st = (d.get("status") or "").lower()
    if status == 200 and st == "success":
        return "success", (d.get("amount") or 0) / 100.0, (d.get("currency") or "").upper()
    if st in ("failed", "abandoned", "reversed"):
        return "failed", 0, ""
    return "pending", 0, ""


PROVIDERS_BILLING = {"cinetpay": (_start_cinetpay, _check_cinetpay), "paystack": (_start_paystack, _check_paystack)}


def _settle(ref: str) -> dict:
    """Ask the provider about one payment; credit Pro exactly once if it really succeeded."""
    with _db_lock:
        con = _billing_db()
        try:
            row = con.execute("SELECT email, provider, plan, amount, currency, status, credited FROM payments"
                              " WHERE reference=?", (ref,)).fetchone()
        finally:
            con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown payment.")
    email, provider, plan, amount, currency, status, credited = row
    if credited:
        return {"status": "success", "email": email}
    if provider not in PROVIDERS_BILLING:
        return {"status": status, "email": email}
    result, paid_amount, paid_currency = PROVIDERS_BILLING[provider][1](ref)
    if result == "success" and (paid_currency != currency or paid_amount + 0.001 < float(amount)):
        result = "failed"                          # paid the wrong amount: never credit
        detail = f"amount mismatch: got {paid_amount} {paid_currency}, expected {amount} {currency}"
    else:
        detail = ""
    with _db_lock:
        con = _billing_db()
        try:
            cur = con.execute("SELECT credited FROM payments WHERE reference=?", (ref,)).fetchone()
            if result == "success" and not cur[0]:
                urow = con.execute("SELECT pro_until FROM users WHERE email=?", (email,)).fetchone()
                start = max(time.time(), (urow[0] if urow else 0) or 0)
                con.execute("UPDATE users SET pro_until=? WHERE email=?",
                            (start + PLAN_DAYS.get(plan, 30) * 86400, email))
                con.execute("UPDATE payments SET status='success', credited=1, updated=? WHERE reference=?",
                            (time.time(), ref))
            elif result != "success":
                con.execute("UPDATE payments SET status=?, updated=?, detail=? WHERE reference=? AND credited=0",
                            (result, time.time(), detail, ref))
            con.commit()
        finally:
            con.close()
    return {"status": result, "email": email}


@app.post("/billing/checkout")
def billing_checkout(request: Request, data: dict = Body(...)):
    email = _email_from_auth(request)
    user = _billing_user(email)
    country = (data.get("country") or user["country"] or "").upper()
    opts = catalog.options_for(country)
    plan = next((p for p in opts["plans"] if p["id"] == data.get("plan")), None)
    method = next((m for m in opts["methods"] if m["id"] == data.get("method")), None)
    if not plan or not method:
        raise HTTPException(status_code=422, detail="That plan or payment method isn't available for your country.")
    ref = "GINK" + secrets.token_hex(10).upper()      # letters+digits only (CinetPay-safe)
    now = time.time()
    with _db_lock:
        con = _billing_db()
        try:
            recent = con.execute("SELECT COUNT(*) FROM payments WHERE email=? AND created > ?",
                                 (email, now - 3600)).fetchone()[0]
            if recent >= 10:
                raise HTTPException(status_code=429, detail="Too many payment attempts. Try again in an hour.")
            # saved BEFORE showing the checkout, as the providers recommend
            con.execute("INSERT INTO payments (reference, email, provider, plan, method, amount, currency, status,"
                        " created, updated) VALUES (?,?,?,?,?,?,?, 'pending', ?, ?)",
                        (ref, email, method["provider"], plan["id"], method["id"], plan["price"], plan["currency"], now, now))
            con.commit()
        finally:
            con.close()
    start = PROVIDERS_BILLING[method["provider"]][0]
    url = start(ref, email, user["name"], plan["id"], method["id"], plan["price"], plan["currency"],
                country, _public_base(request))
    return {"payment_url": url, "reference": ref, "amount": plan["display"]}


@app.get("/billing/status")
def billing_status(request: Request, reference: str = ""):
    email = _email_from_auth(request)
    payment = None
    if reference:
        with _db_lock:
            con = _billing_db()
            try:
                row = con.execute("SELECT email, status FROM payments WHERE reference=?", (reference,)).fetchone()
            finally:
                con.close()
        if not row or row[0] != email:
            raise HTTPException(status_code=404, detail="Unknown payment.")
        payment = row[1]
        if payment == "pending":
            # notifications can't reach a server on a home computer, so the app's
            # polling also triggers a direct check with the provider
            try:
                payment = _settle(reference)["status"]
            except HTTPException:
                raise
            except Exception:
                payment = "pending"
    return {**_plan_status(email), "payment": payment}


@app.api_route("/billing/notify/cinetpay", methods=["GET", "POST"])
async def cinetpay_notify(request: Request):
    if request.method == "GET":
        return {"ok": True}                       # CinetPay pings the URL with GET
    form = dict(await request.form())
    ref = form.get("cpm_trans_id", "")
    if form.get("cpm_site_id") and form.get("cpm_site_id") != _env("CINETPAY_SITE_ID"):
        return {"ok": False}
    if ref:
        import asyncio as _asyncio
        try:
            await _asyncio.get_event_loop().run_in_executor(None, _settle, ref)
        except HTTPException:
            pass
    return {"ok": True}


@app.post("/billing/webhook/paystack")
async def paystack_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(_env("PAYSTACK_SECRET_KEY").encode(), raw, hashlib.sha512).hexdigest()
    if not _env("PAYSTACK_SECRET_KEY") or not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Bad signature.")
    event = _json.loads(raw or b"{}")
    ref = (event.get("data") or {}).get("reference", "")
    if event.get("event") == "charge.success" and ref:
        import asyncio as _asyncio
        try:
            await _asyncio.get_event_loop().run_in_executor(None, _settle, ref)
        except HTTPException:
            pass
    return {"ok": True}


@app.get("/billing/return")
def billing_return(ref: str = ""):
    try:
        res = _settle(ref) if ref else {"status": "pending"}
    except HTTPException:
        res = {"status": "failed"}
    except Exception:
        res = {"status": "pending"}
    if res["status"] == "success":
        return HTMLResponse(_result_page(True, "Go back to Gink \u2014 you can close this tab.", "Gink Pro is active"))
    if res["status"] == "pending":
        return HTMLResponse(_result_page(True, "If you approved it on your phone, Gink will update in a moment "
                                               "\u2014 you can close this tab.", "Checking your payment"))
    return HTMLResponse(_result_page(False, "Nothing was charged for Gink Pro. You can try again from Gink.",
                                     "Payment didn't go through"))


# =====================================================================
# Gink Cloud AI: the app talks to THIS server, never to Groq directly, so
# no AI key ships inside the app. The routes mirror Groq's OpenAI-style API,
# so the official groq library just points its base_url here and sends the
# user's session token in place of an API key.
#
#   POST /ai/openai/v1/chat/completions   (stream or not; tools allowed)
#   GET  /ai/openai/v1/models
#   GET  /ai/usage
#
# Limits (env, per UTC day): GINK_FREE_DAILY (30), GINK_PRO_DAILY (500).
# A "message" is one X-Gink-Turn id, so the action agent's several AI
# rounds for one request count once (capped at MAX_CALLS_PER_TURN).
# Photos are a Pro feature. Answer length is capped per plan.
# Server env: GROQ_API_KEY.
# =====================================================================
GROQ_BASE = os.environ.get("GINK_GROQ_BASE", "https://api.groq.com/openai/v1")   # override only for testing
MAX_CALLS_PER_TURN = 10
MAX_TOKENS = {"free": 1024, "pro": 4096}
_models_cache = {"at": 0.0, "data": None}


def _limit(plan: str) -> int:
    key = "GINK_PRO_DAILY" if plan == "pro" else "GINK_FREE_DAILY"
    try:
        return int(os.environ.get(key, "500" if plan == "pro" else "30"))
    except ValueError:
        return 500 if plan == "pro" else 30


def _usage_db():
    con = _billing_db()
    con.execute("CREATE TABLE IF NOT EXISTS ai_usage (email TEXT NOT NULL, day TEXT NOT NULL,"
                " messages INTEGER NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0,"
                " PRIMARY KEY (email, day))")
    con.execute("CREATE TABLE IF NOT EXISTS ai_turns (email TEXT NOT NULL, turn TEXT NOT NULL, day TEXT NOT NULL,"
                " calls INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (email, turn))")
    return con


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _ai_error(status: int, message: str, code: str):
    from fastapi.responses import JSONResponse
    # x-should-retry: false -- the groq library otherwise retries 429s, which
    # can't help with a daily limit (it only slows the answer down)
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": "gink_" + code, "code": code}},
                        headers={"x-should-retry": "false"})


def _usage_for(email: str) -> dict:
    plan = _plan_status(email)["plan"]
    with _db_lock:
        con = _usage_db()
        try:
            row = con.execute("SELECT messages FROM ai_usage WHERE email=? AND day=?", (email, _today())).fetchone()
        finally:
            con.close()
    used = row[0] if row else 0
    tomorrow = (int(time.time() // 86400) + 1) * 86400
    images = 0
    with _db_lock:
        con = _usage_db()
        try:
            if "images" in {r[1] for r in con.execute("PRAGMA table_info(ai_usage)").fetchall()}:
                r = con.execute("SELECT images FROM ai_usage WHERE email=? AND day=?", (email, _today())).fetchone()
                images = (r[0] if r else 0) or 0
        finally:
            con.close()
    return {"plan": plan, "used": used, "limit": _limit(plan), "resets_at": tomorrow,
            "images_used": images, "images_limit": _image_limit(plan)}


def _count_call(email: str, turn: str, plan: str):
    """Returns an error response if over the limit, else None (and records the call)."""
    day = _today()
    with _db_lock:
        con = _usage_db()
        try:
            new_message = True
            if turn:
                t = con.execute("SELECT calls FROM ai_turns WHERE email=? AND turn=?", (email, turn)).fetchone()
                if t:
                    if t[0] >= MAX_CALLS_PER_TURN:
                        return _ai_error(429, "That request needed too many steps. Try asking in a simpler way.", "turn_limit")
                    new_message = False
            row = con.execute("SELECT messages FROM ai_usage WHERE email=? AND day=?", (email, day)).fetchone()
            used = row[0] if row else 0
            if new_message and used >= _limit(plan):
                if plan == "pro":
                    msg = f"You've reached today's limit of {_limit(plan)} messages. It resets at midnight (UTC)."
                else:
                    msg = (f"You've used today's {_limit(plan)} free messages. They reset at midnight (UTC) "
                           f"\u2014 or upgrade to Gink Pro for {_limit('pro')} a day.")
                return _ai_error(429, msg, "daily_limit")
            con.execute("INSERT INTO ai_usage (email, day, messages, calls) VALUES (?, ?, ?, 1)"
                        " ON CONFLICT(email, day) DO UPDATE SET messages = messages + ?, calls = calls + 1",
                        (email, day, int(new_message), int(new_message)))
            if turn:
                con.execute("INSERT INTO ai_turns (email, turn, day, calls) VALUES (?, ?, ?, 1)"
                            " ON CONFLICT(email, turn) DO UPDATE SET calls = calls + 1", (email, turn[:64], day))
                con.execute("DELETE FROM ai_turns WHERE day < ?", (time.strftime("%Y-%m-%d", time.gmtime(time.time() - 2 * 86400)),))
            con.commit()
        finally:
            con.close()
    return None


def _has_images(messages) -> bool:
    for m in messages or []:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in c):
            return True
    return False


@app.get("/ai/usage")
def ai_usage(request: Request):
    return _usage_for(_email_from_auth(request))


@app.get("/ai/openai/v1/models")
async def ai_models(request: Request):
    _email_from_auth(request)
    if not _env("GROQ_API_KEY"):
        return _ai_error(503, "AI isn't set up on this server yet.", "not_configured")
    if _models_cache["data"] and time.time() - _models_cache["at"] < 600:
        return _models_cache["data"]
    import httpx
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {_env('GROQ_API_KEY')}"})
    if r.status_code != 200:
        return _ai_error(502, "Couldn't list AI models right now.", "upstream")
    data = r.json()
    data["data"] = list(data.get("data", [])) + [{"id": m, "object": "model", "owned_by": "anthropic"}
                                                  for m in sorted(await _live_claude_models())]
    _models_cache.update(at=time.time(), data=data)
    return _models_cache["data"]


# ---- Groq retires models (llama-3.3-70b-versatile and llama-3.1-8b-instant on 16 Aug 2026).
# Apps already installed keep asking for old names, so the server swaps any model Groq no
# longer lists for the best current one -- checked against Groq's live list (cached 1 hour).
RETIRED_MODELS = {
    "llama-3.1-8b-instant": "openai/gpt-oss-20b", "llama3-8b-8192": "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b", "llama3-70b-8192": "openai/gpt-oss-120b",
    "mixtral-8x7b-32768": "openai/gpt-oss-120b", "deepseek-r1-distill-llama-70b": "openai/gpt-oss-120b",
    "moonshotai/kimi-k2-instruct": "openai/gpt-oss-120b", "qwen/qwen3-32b": "openai/gpt-oss-120b",
}
TEXT_MODELS_BEST_FIRST = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b")
VISION_MODELS_BEST_FIRST = ("qwen/qwen3.6-27b", "meta-llama/llama-4-scout-17b-16e-instruct",
                            "meta-llama/llama-4-maverick-17b-128e-instruct")
_groq_models = {"ids": set(), "at": 0.0}


async def _live_groq_models() -> set:
    if time.time() - _groq_models["at"] < 3600 and _groq_models["ids"]:
        return _groq_models["ids"]
    import httpx
    key = _env("GROQ_API_KEY")
    if not key:
        return set()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {key}"})
        if r.status_code == 200:
            _groq_models.update(ids={m["id"] for m in r.json().get("data", [])}, at=time.time())
    except Exception:
        pass
    return _groq_models["ids"]


async def _current_model(requested: str, needs_vision: bool = False) -> str:
    live = await _live_groq_models()
    if not live:                                       # can't check: at least fix the known retirements
        return RETIRED_MODELS.get(requested, requested)
    if requested in live and not (needs_vision and requested not in VISION_MODELS_BEST_FIRST):
        return requested
    if needs_vision:
        for m in VISION_MODELS_BEST_FIRST:
            if m in live:
                return m
    swap = RETIRED_MODELS.get(requested)
    if swap in live:
        return swap
    for m in TEXT_MODELS_BEST_FIRST:
        if m in live:
            return m
    return requested


def _fit_reasoning(body: dict, cap: int):
    """GPT-OSS reasons before answering, and the reasoning counts toward max_tokens. A short
    limit (old apps ask 24 tokens for a chat title) would be spent on reasoning, leaving an
    empty answer: ask for little reasoning and leave room for it."""
    if not str(body.get("model", "")).startswith("openai/gpt-oss"):
        return
    if (body.get("max_tokens") or 0) <= 300 and "reasoning_effort" not in body:
        body["reasoning_effort"] = "low"
        body["max_tokens"] = min(max(int(body.get("max_tokens") or 0) + 256, 300), cap)


# ---- Claude (Anthropic), through Anthropic's OpenAI-compatible endpoint, so the same request
# and streaming code serves both providers. Pro only (Claude costs much more than Groq), with
# its own daily allowance (GINK_PRO_CLAUDE_DAILY). No ANTHROPIC_API_KEY -> Groq answers instead.
ANTHROPIC_BASE = os.environ.get("GINK_ANTHROPIC_BASE", "https://api.anthropic.com/v1")
CLAUDE_MODELS_BEST_FIRST = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5", "claude-fable-5-1")
# Gink's own names for the Claude models (fastest -> most capable). Apps and developers may use
# either; the server translates. Change a name here and in the apps' pickers.
GINK_MODEL_NAMES = {"gink-flake": "openai/gpt-oss-20b", "gink-crystal": "openai/gpt-oss-120b",      # Free (Groq)
                    "gink-prism": "qwen/qwen3.6-27b",
                    "gink-flurry": "claude-haiku-5-5", "gink-frost": "claude-sonnet-5-5",           # Pro (Claude)
                    "gink-glacier": "claude-opus-5-5", "gink-aurora": "claude-fable-5-1"}
_claude_models = {"ids": set(), "at": 0.0}


async def _live_claude_models() -> set:
    if not _env("ANTHROPIC_API_KEY"):
        return set()
    if time.time() - _claude_models["at"] < 3600 and _claude_models["ids"]:
        return _claude_models["ids"]
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{ANTHROPIC_BASE}/models", params={"limit": 100},
                                 headers={"x-api-key": _env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
        if r.status_code == 200:
            ids = {m["id"] for m in r.json().get("data", []) if str(m.get("id", "")).startswith("claude-")}
            if ids:
                _claude_models.update(ids=ids, at=time.time())
    except Exception:
        pass
    return _claude_models["ids"] or set(CLAUDE_MODELS_BEST_FIRST)


async def _current_claude_model(requested: str) -> str:
    live = await _live_claude_models()
    if requested in live:
        return requested
    for m in CLAUDE_MODELS_BEST_FIRST:
        if m in live:
            return m
    return sorted(live)[0] if live else CLAUDE_MODELS_BEST_FIRST[0]


def _count_claude(email: str, turn: str = ""):
    """Pro's daily Claude allowance (one question = one, however many calls it takes)."""
    limit = int(os.environ.get("GINK_PRO_CLAUDE_DAILY", "50"))
    day = _today()
    with _db_lock:
        con = _usage_db()
        try:
            con.execute("CREATE TABLE IF NOT EXISTS claude_usage (email TEXT, day TEXT, n INTEGER, PRIMARY KEY (email, day))")
            con.execute("CREATE TABLE IF NOT EXISTS claude_turns (email TEXT, turn TEXT, day TEXT, PRIMARY KEY (email, turn))")
            if turn and con.execute("SELECT 1 FROM claude_turns WHERE email=? AND turn=?", (email, turn)).fetchone():
                return None                                   # same question, already counted
            row = con.execute("SELECT n FROM claude_usage WHERE email=? AND day=?", (email, day)).fetchone()
            used = row[0] if row else 0
            if used >= limit:
                return _ai_error(429, f"You've used today's {limit} Claude messages. Other Gink models still work, "
                                      "and Claude is back tomorrow.", "daily_limit")
            con.execute("INSERT INTO claude_usage (email, day, n) VALUES (?, ?, 1) ON CONFLICT(email, day) DO UPDATE SET n = n + 1",
                        (email, day))
            if turn:
                con.execute("INSERT OR IGNORE INTO claude_turns (email, turn, day) VALUES (?, ?, ?)", (email, turn, day))
            con.commit()
        finally:
            con.close()
    return None


# ---- Claude through the NATIVE Messages API (default), with automatic prompt caching:
# the repeated start of every request (instructions, tools, earlier messages) is read from
# Anthropic's cache at 0.1x the input price. Apps keep speaking the OpenAI format; these
# functions translate requests, answers, tool calls and the live stream both ways.
# GINK_CLAUDE_MODE=compat switches back to Anthropic's OpenAI-compatible endpoint.
_FINISH = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "tool_use": "tool_calls",
           "pause_turn": "stop", "refusal": "content_filter"}


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in (content or []) if isinstance(p, dict) and p.get("type") == "text")


def _claude_parts(content) -> list:
    """OpenAI message content -> Claude content blocks (text and images)."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    out = []
    for part in content or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            out.append({"type": "text", "text": part["text"]})
        elif part.get("type") == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if url.startswith("data:") and ";base64," in url:
                media, data = url[5:].split(";base64,", 1)
                out.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
            elif url.startswith("https://"):
                out.append({"type": "image", "source": {"type": "url", "url": url}})
    return out


def _to_claude(body: dict) -> dict:
    """OpenAI chat request -> Claude Messages request (+ automatic prompt caching)."""
    system, messages = [], []

    def add(role, blocks):
        if not blocks:
            return
        if messages and messages[-1]["role"] == role:          # Claude wants alternating turns
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": list(blocks)})

    for m in body.get("messages") or []:
        role = m.get("role")
        if role in ("system", "developer"):
            t = _text_of(m.get("content"))
            if t:
                system.append(t)
        elif role == "user":
            add("user", _claude_parts(m.get("content")))
        elif role == "assistant":
            blocks = _claude_parts(m.get("content"))
            for call in m.get("tool_calls") or []:
                fn = call.get("function") or {}
                try:
                    args = _json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append({"type": "tool_use", "id": call.get("id") or "call_" + secrets.token_hex(6),
                               "name": fn.get("name", ""), "input": args if isinstance(args, dict) else {"value": args}})
            add("assistant", blocks)
        elif role == "tool":
            add("user", [{"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                          "content": _text_of(m.get("content")) or "(no output)"}])
    out = {"model": body["model"], "max_tokens": int(body.get("max_tokens") or 1024), "messages": messages,
           "cache_control": {"type": "ephemeral"}}
    if system:
        out["system"] = "\n\n".join(system)
    if body.get("temperature") is not None:
        out["temperature"] = max(0.0, min(1.0, float(body["temperature"])))
    stop = body.get("stop")
    if stop:
        out["stop_sequences"] = [stop] if isinstance(stop, str) else list(stop)[:4]
    tools = [t.get("function") or {} for t in body.get("tools") or [] if t.get("type", "function") == "function"]
    if tools:
        out["tools"] = [{"name": f.get("name", ""), "description": f.get("description", ""),
                         "input_schema": f.get("parameters") or {"type": "object", "properties": {}}} for f in tools]
        choice = body.get("tool_choice", "auto")
        if choice == "none":
            out["tool_choice"] = {"type": "none"}
        elif choice == "required":
            out["tool_choice"] = {"type": "any"}
        elif isinstance(choice, dict) and (choice.get("function") or {}).get("name"):
            out["tool_choice"] = {"type": "tool", "name": choice["function"]["name"]}
        else:
            out["tool_choice"] = {"type": "auto"}
    if body.get("stream"):
        out["stream"] = True
    return out


def _usage_from_claude(u: dict) -> dict:
    u = u or {}
    cached, written = u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0
    prompt = (u.get("input_tokens") or 0) + cached + written
    return {"prompt_tokens": prompt, "completion_tokens": u.get("output_tokens") or 0,
            "total_tokens": prompt + (u.get("output_tokens") or 0), "prompt_tokens_details": {"cached_tokens": cached}}


def _from_claude(resp: dict, model: str) -> dict:
    """Claude Messages answer -> OpenAI chat completion."""
    text, calls = [], []
    for block in resp.get("content") or []:
        if block.get("type") == "text":
            text.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append({"id": block.get("id"), "type": "function",
                          "function": {"name": block.get("name"), "arguments": _json.dumps(block.get("input") or {})}})
    message = {"role": "assistant", "content": "".join(text) or (None if calls else "")}
    if calls:
        message["tool_calls"] = calls
    return {"id": resp.get("id", "chatcmpl-claude"), "object": "chat.completion", "created": int(time.time()),
            "model": model, "choices": [{"index": 0, "message": message,
                                         "finish_reason": _FINISH.get(resp.get("stop_reason"), "stop")}],
            "usage": _usage_from_claude(resp.get("usage"))}


class _ClaudeStream:
    """Claude's stream events -> OpenAI 'chat.completion.chunk' lines (text and tool calls)."""

    def __init__(self, model: str):
        self.model, self.id, self.tool_index, self.blocks = model, "chatcmpl-claude", -1, {}

    def _chunk(self, delta: dict, finish=None) -> bytes:
        c = {"id": self.id, "object": "chat.completion.chunk", "created": int(time.time()), "model": self.model,
             "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        return ("data: " + _json.dumps(c) + "\n\n").encode()

    def event(self, ev: dict) -> list:
        kind = ev.get("type")
        if kind == "message_start":
            self.id = (ev.get("message") or {}).get("id", self.id)
            return [self._chunk({"role": "assistant", "content": ""})]
        if kind == "content_block_start":
            block = ev.get("content_block") or {}
            if block.get("type") == "tool_use":
                self.tool_index += 1
                self.blocks[ev.get("index")] = self.tool_index
                return [self._chunk({"tool_calls": [{"index": self.tool_index, "id": block.get("id"), "type": "function",
                                                     "function": {"name": block.get("name"), "arguments": ""}}]})]
            return []
        if kind == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta":
                return [self._chunk({"content": d.get("text", "")})]
            if d.get("type") == "input_json_delta" and ev.get("index") in self.blocks:
                return [self._chunk({"tool_calls": [{"index": self.blocks[ev["index"]],
                                                     "function": {"arguments": d.get("partial_json", "")}}]})]
            return []
        if kind == "message_delta":
            reason = (ev.get("delta") or {}).get("stop_reason")
            return [self._chunk({}, _FINISH.get(reason, "stop"))] if reason else []
        if kind == "message_stop":
            return [b"data: [DONE]\n\n"]
        if kind == "error":
            err = ev.get("error") or {}
            msg = "The AI service is busy. Please try again." if err.get("type") == "overloaded_error" else \
                  "The AI service had a problem. Please try again."
            return [("data: " + _json.dumps({"error": {"message": msg, "type": "gink_upstream", "code": "upstream"}}) + "\n\n").encode(),
                    b"data: [DONE]\n\n"]
        return []


async def _claude_native(body: dict):
    """Send an OpenAI-format request to Claude's Messages API; answer in OpenAI format."""
    import httpx
    from fastapi.responses import JSONResponse, StreamingResponse
    req = _to_claude(body)
    headers = {"x-api-key": _env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01", "content-type": "application/json"}
    url = f"{ANTHROPIC_BASE}/messages"

    def upstream_error(status, raw):
        try:
            err = _json.loads(raw).get("error") or {}
        except Exception:
            err = {}
        if status == 400 and err.get("message"):
            return _ai_error(400, "Claude couldn't use this request: " + str(err["message"])[:300], "bad_request")
        if status in (429, 529):
            return _ai_error(503, "Claude is busy right now. Please try again in a moment, or pick another model.", "upstream")
        return _ai_error(502, "The AI service had a problem. Please try again.", "upstream")

    if not req.get("stream"):
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
            r = await client.post(url, json=req, headers=headers)
        if r.status_code != 200:
            return upstream_error(r.status_code, r.text)
        return JSONResponse(_from_claude(r.json(), body["model"]))

    client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15))
    upstream = await client.send(client.build_request("POST", url, json=req, headers=headers), stream=True)
    if upstream.status_code != 200:
        raw = await upstream.aread()
        await upstream.aclose(); await client.aclose()
        return upstream_error(upstream.status_code, raw.decode("utf-8", "replace"))
    translator = _ClaudeStream(body["model"])

    async def relay():
        buf = ""
        try:
            async for piece in upstream.aiter_text():
                buf += piece
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    data = "".join(line[5:].strip() for line in frame.splitlines() if line.startswith("data:"))
                    if not data:
                        continue
                    try:
                        ev = _json.loads(data)
                    except ValueError:
                        continue
                    for out in translator.event(ev):
                        yield out
        finally:
            await upstream.aclose(); await client.aclose()
    return StreamingResponse(relay(), media_type="text/event-stream")


@app.post("/ai/openai/v1/chat/completions")
async def ai_chat(request: Request):
    email = _email_from_auth(request)
    if not _env("GROQ_API_KEY"):
        return _ai_error(503, "AI isn't set up on this server yet.", "not_configured")
    try:
        body = await request.json()
    except Exception:
        return _ai_error(400, "Bad request.", "bad_request")
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list) or not body.get("model"):
        return _ai_error(400, "Bad request.", "bad_request")
    if len(_json.dumps(body)) > 12_000_000:
        return _ai_error(413, "That message is too large.", "too_large")
    plan = _plan_status(email)["plan"]
    if _has_images(body["messages"]) and plan != "pro":
        return _ai_error(403, "Looking at photos is part of Gink Pro.", "pro_required")
    # the app groups one question's calls under X-Gink-Turn; API callers can't (every API call counts)
    turn = "" if getattr(request.state, "gink_api_email", None) else request.headers.get("x-gink-turn", "")
    # Claude (Anthropic) or Groq: decided once, here
    body["model"] = GINK_MODEL_NAMES.get(str(body["model"]).lower(), body["model"])   # "gink-frost" -> Claude Sonnet
    wants_claude = str(body["model"]).startswith("claude-")
    if wants_claude and not _env("ANTHROPIC_API_KEY"):
        wants_claude, body["model"] = False, TEXT_MODELS_BEST_FIRST[0]   # no Anthropic key here: Groq instead
    if wants_claude and plan != "pro":
        return _ai_error(403, "Claude models are part of Gink Pro.", "pro_required")
    blocked = _count_call(email, turn, plan)
    if blocked is not None:
        return blocked
    if wants_claude:
        blocked = _count_claude(email, turn)
        if blocked is not None:
            return blocked
    body["max_tokens"] = min(int(body.get("max_tokens") or MAX_TOKENS[plan]), MAX_TOKENS[plan])
    if wants_claude:
        body["model"] = await _current_claude_model(str(body["model"]))
        body.pop("reasoning_effort", None)
        body.pop("user", None)
        base, key = ANTHROPIC_BASE, _env("ANTHROPIC_API_KEY")
    else:
        body["model"] = await _current_model(str(body["model"]), _has_images(body["messages"]))
        _fit_reasoning(body, MAX_TOKENS[plan])
        body["user"] = hashlib.sha256(email.encode()).hexdigest()[:32]   # abuse tracing without sharing the email
        base, key = GROQ_BASE, _env("GROQ_API_KEY")
    if wants_claude and os.environ.get("GINK_CLAUDE_MODE", "native") != "compat":
        return await _claude_native(body)                 # native Messages API + prompt caching
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    import httpx
    from fastapi.responses import JSONResponse, StreamingResponse
    if body.get("stream"):
        client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15))
        req = client.build_request("POST", f"{base}/chat/completions", json=body, headers=headers)
        upstream = await client.send(req, stream=True)
        if upstream.status_code != 200:
            text = await upstream.aread()
            await upstream.aclose()
            await client.aclose()
            try:
                return JSONResponse(status_code=upstream.status_code, content=_json.loads(text))
            except ValueError:
                return _ai_error(502, "The AI service had a problem. Please try again.", "upstream")

        async def relay():
            try:
                # aiter_bytes (not aiter_raw): decompressed, because the
                # Content-Encoding header isn't passed on to the app
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()
        return StreamingResponse(relay(), media_type="text/event-stream")
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base}/chat/completions", json=body, headers=headers)
    try:
        return JSONResponse(status_code=r.status_code, content=r.json())
    except ValueError:
        return _ai_error(502, "The AI service had a problem. Please try again.", "upstream")


# =====================================================================
# Account & app info (Settings window)
#
#   GET    /info              public: support email, privacy/terms links
#   GET    /billing/history   (auth) the user's payments
#   POST   /account/delete    (auth) {"confirm": "DELETE"} -- deletes the account
#                             and everything synced; payment records are kept
#                             for accounting but no longer linked to the person.
# =====================================================================
@app.get("/info")
def app_info():
    return {"support_email": _env("GINK_SUPPORT_EMAIL"), "privacy_url": _env("GINK_PRIVACY_URL"),
            "terms_url": _env("GINK_TERMS_URL"), "help_url": _env("GINK_HELP_URL")}


@app.get("/billing/history")
def billing_history(request: Request):
    email = _email_from_auth(request)
    with _db_lock:
        con = _billing_db()
        try:
            rows = con.execute("SELECT reference, plan, method, amount, currency, status, created FROM payments"
                               " WHERE email=? ORDER BY created DESC LIMIT 50", (email,)).fetchall()
        finally:
            con.close()
    return {"payments": [{"reference": r[0], "plan": r[1], "method": r[2], "amount": r[3], "currency": r[4],
                          "status": r[5], "created": r[6],
                          "display": catalog.format_price(r[3], r[4])} for r in rows]}


@app.post("/account/delete")
def delete_account(request: Request, data: dict = Body(...)):
    email = _email_from_auth(request)
    if (data.get("confirm") or "") != "DELETE":
        raise HTTPException(status_code=422, detail='Type DELETE to confirm.')
    anon = "deleted:" + hashlib.sha256(email.encode()).hexdigest()[:16]
    with _db_lock:
        con = _usage_db()
        try:
            _sync_db().close()                     # make sure every table exists
            con.execute("CREATE TABLE IF NOT EXISTS sync_docs (email TEXT, kind TEXT, doc_id TEXT, payload TEXT,"
                        " updated REAL, deleted INTEGER, server_ts REAL, PRIMARY KEY (email, kind, doc_id))")
            con.execute(_API_KEYS_TABLE)
            con.execute("CREATE TABLE IF NOT EXISTS claude_usage (email TEXT, day TEXT, n INTEGER, PRIMARY KEY (email, day))")
            con.execute("CREATE TABLE IF NOT EXISTS claude_turns (email TEXT, turn TEXT, day TEXT, PRIMARY KEY (email, turn))")
            for table in ("users", "sync_docs", "ai_usage", "ai_turns", "api_keys", "claude_usage", "claude_turns"):
                con.execute(f"DELETE FROM {table} WHERE email=?", (email,))
            con.execute("UPDATE payments SET email=? WHERE email=?", (anon, email))
            con.execute("CREATE TABLE IF NOT EXISTS deleted_accounts (email TEXT PRIMARY KEY, at REAL NOT NULL)")
            con.execute("INSERT OR REPLACE INTO deleted_accounts (email, at) VALUES (?, ?)", (email, time.time()))
            con.commit()
        finally:
            con.close()
    with _otp_lock:
        for store in (_otp_store, _pending_signups, _reset_codes, _login_failures):
            store.pop(email, None)
    return {"deleted": True}


# =====================================================================
# Answer feedback (thumbs up / down under Gink's replies)
#   POST /feedback  (auth) {"rating": "up"|"down", "reason": "", "model": "", "chars": 0}
# Stores NO message text and no email -- only the rating, an optional
# reason from a fixed list, the model, the reply length and a hashed user
# id (to spot one user flooding). GET /feedback/summary (owner key) shows
# totals per model so you can see which answers people dislike.
# =====================================================================
FEEDBACK_REASONS = {"", "wrong", "not_helpful", "too_long", "unsafe", "other"}


def _feedback_db():
    con = _db()
    con.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL,"
                " rating TEXT NOT NULL, reason TEXT, model TEXT, chars INTEGER, created REAL NOT NULL)")
    return con


@app.post("/feedback")
def feedback(request: Request, data: dict = Body(...)):
    email = _email_from_auth(request)
    rating = data.get("rating")
    reason = (data.get("reason") or "").strip()
    if rating not in ("up", "down") or reason not in FEEDBACK_REASONS:
        raise HTTPException(status_code=422, detail="Bad feedback.")
    user = hashlib.sha256(email.encode()).hexdigest()[:16]
    with _db_lock:
        con = _feedback_db()
        try:
            recent = con.execute("SELECT COUNT(*) FROM feedback WHERE user=? AND created > ?",
                                 (user, time.time() - 3600)).fetchone()[0]
            if recent >= 120:
                raise HTTPException(status_code=429, detail="Thanks \u2014 that's plenty of feedback for now.")
            con.execute("INSERT INTO feedback (user, rating, reason, model, chars, created) VALUES (?,?,?,?,?,?)",
                        (user, rating, reason, str(data.get("model") or "")[:80], int(data.get("chars") or 0), time.time()))
            con.commit()
        finally:
            con.close()
    return {"ok": True}


@app.get("/feedback/summary")
def feedback_summary(request: Request):
    key = _env("GINK_ADMIN_KEY")
    if not key or not hmac.compare_digest(request.headers.get("x-admin-key", ""), key):
        raise HTTPException(status_code=403, detail="Owner only.")
    with _db_lock:
        con = _feedback_db()
        try:
            rows = con.execute("SELECT model, rating, reason, COUNT(*) FROM feedback WHERE created > ?"
                               " GROUP BY model, rating, reason", (time.time() - 30 * 86400,)).fetchall()
        finally:
            con.close()
    return {"last_30_days": [{"model": m, "rating": r, "reason": why, "count": n} for m, r, why, n in rows]}


# =====================================================================
# Media: image generation through YOUR server (no Google key in the app).
#   POST /media/image  (auth) {"prompt", "aspect_ratio": "1:1", "style": ""}
#   -> {"image_b64", "mime_type", "model", "used", "limit"}
# Google's Nano Banana models via the Interactions API
# (https://ai.google.dev/gemini-api/docs/image-generation). Google retires
# image models often (Imagen 3 Nov 2025, Imagen 4 Aug 2026), so the model
# is a setting: GINK_IMAGE_MODEL (default gemini-nano-banana-2.1).
# Images cost money per picture, so they have their own daily limits:
# GINK_FREE_IMAGES (3) and GINK_PRO_IMAGES (50).
# =====================================================================
IMAGE_ASPECTS = {"1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
GEMINI_INTERACTIONS = "https://generativelanguage.googleapis.com/v1beta/interactions"


def _image_limit(plan: str) -> int:
    key, default = ("GINK_PRO_IMAGES", 50) if plan == "pro" else ("GINK_FREE_IMAGES", 3)
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


def _extract_image(resp: dict):
    """(base64 data, mime) of the final image -- from output_image, or the last
    image in a model_output step (thought images are skipped)."""
    out = resp.get("output_image")
    if isinstance(out, dict) and out.get("data"):
        return out["data"], out.get("mime_type") or "image/png"
    found = None
    for step in resp.get("steps") or []:
        if step.get("type") == "model_output":
            for block in step.get("content") or []:
                if block.get("type") == "image" and block.get("data"):
                    found = (block["data"], block.get("mime_type") or "image/png")
    return found if found else (None, None)


@app.post("/media/image")
async def media_image(request: Request):
    email = _email_from_auth(request)
    if not _env("GEMINI_API_KEY"):
        return _ai_error(503, "Image creation isn't set up on this server yet.", "not_configured")
    try:
        data = await request.json()
    except Exception:
        return _ai_error(400, "Bad request.", "bad_request")
    prompt = " ".join(str(data.get("prompt") or "").split())[:4000]
    aspect = data.get("aspect_ratio") or "1:1"
    if not prompt:
        return _ai_error(422, "Describe the image you want.", "bad_request")
    if aspect not in IMAGE_ASPECTS:
        aspect = "1:1"
    style = str(data.get("style") or "")[:200]
    plan = _plan_status(email)["plan"]
    day, limit = _today(), _image_limit(plan)
    with _db_lock:
        con = _usage_db()
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(ai_usage)").fetchall()}
            if "images" not in cols:
                con.execute("ALTER TABLE ai_usage ADD COLUMN images INTEGER NOT NULL DEFAULT 0")
            row = con.execute("SELECT images FROM ai_usage WHERE email=? AND day=?", (email, day)).fetchone()
            used = (row[0] if row else 0) or 0
            if used >= limit:
                msg = (f"You've created today's {limit} images. More tomorrow \u2014 or upgrade to Gink Pro for "
                       f"{_image_limit('pro')} a day." if plan != "pro" else
                       f"You've reached today's limit of {limit} images. It resets at midnight (UTC).")
                return _ai_error(429, msg, "daily_limit")
            # count BEFORE the slow call so parallel requests can't slip past the limit
            con.execute("INSERT INTO ai_usage (email, day, messages, calls, images) VALUES (?, ?, 0, 0, 1)"
                        " ON CONFLICT(email, day) DO UPDATE SET images = images + 1", (email, day))
            con.commit()
        finally:
            con.close()
    body = {"model": _env("GINK_IMAGE_MODEL") or "gemini-nano-banana-2.1",
            "input": [{"type": "text", "text": (f"{prompt}. Style: {style}" if style else prompt)}],
            "response_format": {"type": "image", "mime_type": "image/png", "aspect_ratio": aspect, "image_size": "1K"}}
    import httpx

    def refund():
        with _db_lock:
            con = _usage_db()
            try:
                con.execute("UPDATE ai_usage SET images = MAX(images - 1, 0) WHERE email=? AND day=?", (email, day))
                con.commit()
            finally:
                con.close()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(GEMINI_INTERACTIONS, json=body,
                                  headers={"x-goog-api-key": _env("GEMINI_API_KEY"), "Content-Type": "application/json"})
        resp = r.json()
    except Exception:
        refund()
        return _ai_error(502, "The image service didn't answer. Please try again.", "upstream")
    if r.status_code != 200:
        refund()
        detail = ((resp.get("error") or {}).get("message") or "") if isinstance(resp, dict) else ""
        if "safety" in detail.lower() or "policy" in detail.lower() or r.status_code == 400:
            return _ai_error(400, "That image can't be created \u2014 it may break the image service's content rules. "
                                  "Try describing it differently.", "refused")
        return _ai_error(502, "The image service had a problem. Please try again.", "upstream")
    b64, mime = _extract_image(resp)
    if not b64:
        refund()
        return _ai_error(400, "No image came back \u2014 the request may have been declined. Try rephrasing it.", "refused")
    return {"image_b64": b64, "mime_type": mime, "model": body["model"], "used": used + 1, "limit": limit}


# =====================================================================
# Human-sounding speech through YOUR server (no Google key in the app).
#   POST /voice/speak  (auth) {"text", "persona"} -> {"audio_b64", "mime_type": "audio/wav"}
# Google Gemini TTS via the Interactions API
# (https://ai.google.dev/gemini-api/docs/speech-generation). Default model
# gemini-3.8-flash-lite-tts -- Google's model for real-time voice agents
# (GA Sept 2026); set GINK_TTS_MODEL=gemini-3.8-flash-tts for maximum fidelity.
# Google's advice for voice agents, followed here: one call per sentence as
# the reply streams in, a short constant style, and accents from regional
# voices (Extended Voice Library) rather than from style instructions.
# Daily allowance in characters: GINK_FREE_VOICE_CHARS (15 000, ~15 min) and
# GINK_PRO_VOICE_CHARS (200 000). Failed calls are refunded.
# =====================================================================
TTS_PERSONAS = {
    # Gink voice key: (prebuilt Google voice, short constant style, regional search or None)
    "Female (Jenny)": ("Sulafat", "warm, relaxed and conversational", None),
    "Male (Guy)": ("Achird", "friendly, steady and conversational", None),
    "Female (Aria)": ("Laomedeia", "bright, upbeat and conversational", None),
    "Male (Christopher)": ("Charon", "composed, direct and conversational", None),
    "sonia": ("Erinome", "calm, articulate and conversational", {"region_code": "GB", "gender": "female"}),
    "ryan": ("Umbriel", "relaxed, easygoing and conversational", {"region_code": "GB", "gender": "male"}),
    "ezinne": ("Aoede", "cheerful, grounded and conversational", {"region_code": "NG", "gender": "female"}),
    "abeo": ("Orus", "confident, calm and conversational", {"region_code": "NG", "gender": "male"}),
    "asilia": ("Vindemiatrix", "gentle, patient and conversational", {"region_code": "KE", "gender": "female"}),
    "denise": ("Despina", "douce, pos\u00e9e et naturelle", {"language_code": "fr-FR", "gender": "female"}),
    "henri": ("Algieba", "clair, chaleureux et naturel", {"language_code": "fr-FR", "gender": "male"}),
}
_regional_voice_cache: dict = {}
MAX_TTS_CHARS = 1500
_tts_cooldown = {"until": 0.0, "reason": ""}      # Google said "retry in ..." -> don't call it until then


def _retry_seconds(message: str) -> int:
    """'Please retry in 10h58m7s' / 'retry in 50s' -> seconds (60 if unknown)."""
    m = re.search(r"retry in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?", message or "", re.I)
    if not m or not any(m.groups()):
        return 60
    h, mi, se = (float(x) if x else 0 for x in m.groups())
    return max(1, int(h * 3600 + mi * 60 + se))


def _human_wait(sec: float) -> str:
    sec = int(sec)
    if sec < 90:
        return f"{sec} seconds"
    if sec < 5400:
        return f"{round(sec / 60)} minutes"
    return f"{round(sec / 3600, 1):g} hours"


def _voice_limit(plan: str) -> int:
    key, default = ("GINK_PRO_VOICE_CHARS", 200_000) if plan == "pro" else ("GINK_FREE_VOICE_CHARS", 15_000)
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


async def _regional_voice(filters: dict) -> str:
    """A conversational voice from Google's Extended Voice Library for a region
    (e.g. Nigerian English). Cached for a day; "" if none (use the prebuilt one)."""
    key = _json.dumps(filters, sort_keys=True)
    hit = _regional_voice_cache.get(key)
    if hit and time.time() - hit[1] < 86400:
        return hit[0]
    import httpx
    params = [("context", "Conversational"), ("page_size", "20")] + [(k, v) for k, v in filters.items()]
    voice = ""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://generativelanguage.googleapis.com/v1beta/voices", params=params,
                            headers={"x-goog-api-key": _env("GEMINI_API_KEY")})
        if r.status_code == 200:
            for v in r.json().get("voices") or []:
                vid = v.get("id") or v.get("name") or ""
                if vid:
                    voice = vid
                    break
    except Exception:
        voice = ""
    _regional_voice_cache[key] = (voice, time.time())
    return voice


def _extract_audio(resp: dict):
    out = resp.get("output_audio")
    if isinstance(out, dict) and out.get("data"):
        return out["data"], out.get("mime_type") or "audio/wav"
    found = None
    for step in resp.get("steps") or []:
        if step.get("type") == "model_output":
            for block in step.get("content") or []:
                if block.get("type") == "audio" and block.get("data"):
                    found = (block["data"], block.get("mime_type") or "audio/wav")
    return found if found else (None, None)


@app.post("/voice/speak")
async def voice_speak(request: Request):
    email = _email_from_auth(request)
    if not _env("GEMINI_API_KEY"):
        print("[Gink server] Natural voice: GEMINI_API_KEY is not set on this server.")
        return _ai_error(503, "Natural voices aren't set up on this server yet (GEMINI_API_KEY is missing).", "not_configured")
    try:
        data = await request.json()
    except Exception:
        return _ai_error(400, "Bad request.", "bad_request")
    text = " ".join(str(data.get("text") or "").split())[:MAX_TTS_CHARS]
    if not text:
        return _ai_error(422, "Nothing to say.", "bad_request")
    if time.time() < _tts_cooldown["until"]:
        wait = _tts_cooldown["until"] - time.time()
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, headers={"x-should-retry": "false"}, content={"error": {
            "message": "The natural voice is resting.", "code": "voice_busy", "retry_after": int(wait),
            "detail": f"{_tts_cooldown['reason']} \u2014 back in about {_human_wait(wait)}"}})
    voice, style, regional = TTS_PERSONAS.get(str(data.get("persona") or ""), TTS_PERSONAS["Female (Jenny)"])
    style += {"slow": ", speaking slowly", "fast": ", speaking a little quickly"}.get(str(data.get("speed") or ""), "")
    plan = _plan_status(email)["plan"]
    day, limit, n = _today(), _voice_limit(plan), len(text)
    with _db_lock:
        con = _usage_db()
        try:
            if "voice_chars" not in {r[1] for r in con.execute("PRAGMA table_info(ai_usage)").fetchall()}:
                con.execute("ALTER TABLE ai_usage ADD COLUMN voice_chars INTEGER NOT NULL DEFAULT 0")
            row = con.execute("SELECT voice_chars FROM ai_usage WHERE email=? AND day=?", (email, day)).fetchone()
            used = (row[0] if row else 0) or 0
            if used + n > limit:
                return _ai_error(429, "You've used today's natural-voice time. Gink will use its standard voice until "
                                      "tomorrow" + ("" if plan == "pro" else " \u2014 or upgrade to Gink Pro for much more") + ".",
                                 "daily_limit")
            con.execute("INSERT INTO ai_usage (email, day, messages, calls, voice_chars) VALUES (?, ?, 0, 0, ?)"
                        " ON CONFLICT(email, day) DO UPDATE SET voice_chars = voice_chars + ?", (email, day, n, n))
            con.commit()
        finally:
            con.close()

    def refund():
        with _db_lock:
            con = _usage_db()
            try:
                con.execute("UPDATE ai_usage SET voice_chars = MAX(voice_chars - ?, 0) WHERE email=? AND day=?", (n, email, day))
                con.commit()
            finally:
                con.close()
    if regional:
        voice = await _regional_voice(regional) or voice
    body = {"model": _env("GINK_TTS_MODEL") or "gemini-3.8-flash-lite-tts",
            "input": [{"type": "user_input", "content": [{
                "type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio"},                       # WAV (RIFF header) by default
            "generation_config": {"speech_config": [{"voice": voice}]}}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(GEMINI_INTERACTIONS, json=body,
                                  headers={"x-goog-api-key": _env("GEMINI_API_KEY"), "Content-Type": "application/json"})
        resp = r.json()
    except Exception as exc:
        refund()
        print(f"[Gink server] Natural voice: couldn't reach Google ({exc.__class__.__name__}: {exc})")
        return _ai_error(502, "The voice service didn't answer.", "upstream")
    if r.status_code != 200:
        refund()
        detail = ((resp.get("error") or {}).get("message") if isinstance(resp, dict) else "") or f"HTTP {r.status_code}"
        print(f"[Gink server] Natural voice: Google answered {r.status_code} for model {body['model']}, "
              f"voice {voice}: {detail[:400]}")
        if r.status_code == 429:
            # Google's own limit for this key (e.g. Free Tier: 3 a minute, 10 a day): stop calling until it lifts
            wait = _retry_seconds(detail)
            free = "free tier" in detail.lower()
            _tts_cooldown.update(until=time.time() + wait,
                                 reason=("Google's Free Tier limit for voices was reached (enable billing for the key's "
                                         "Google project to lift it)" if free else "Google's rate limit for voices was reached"))
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=503, headers={"x-should-retry": "false"}, content={"error": {
                "message": "The natural voice is resting.", "code": "voice_busy", "retry_after": wait,
                "detail": f"{_tts_cooldown['reason']} \u2014 back in about {_human_wait(wait)}"}})
        err = _ai_error(502, "The voice service had a problem.", "upstream")
        payload = _json.loads(err.body)
        payload["error"]["detail"] = f"Google {r.status_code}: {detail[:300]}"
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content=payload, headers={"x-should-retry": "false"})
    b64, mime = _extract_audio(resp)
    if not b64:
        refund()
        return _ai_error(502, "No audio came back.", "upstream")
    return {"audio_b64": b64, "mime_type": mime or "audio/wav", "voice": voice, "used": used + n, "limit": limit}



# =====================================================================
# Gink on the web:  GET /app  (the web app)   POST /render  (formatting)
# The web app is the app's own chat page plus a browser "bridge"
# (webapp/bridge.js), pre-built by tools/build_web_app.py into web_app/.
# It talks only to THIS server (Content-Security-Policy connect-src 'self').
# =====================================================================
WEB_APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_app")
_WEB_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data: blob: https:; media-src 'self' data: blob:; connect-src 'self'; "
                                "font-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "microphone=(self), camera=()",
    "Cache-Control": "no-cache",
}


@app.get("/app", response_class=HTMLResponse)
@app.get("/app/", response_class=HTMLResponse)
def web_app_page():
    path = os.path.join(WEB_APP_DIR, "index.html")
    if not os.path.isfile(path):
        return HTMLResponse("Gink on the web isn't built yet: run  python tools/build_web_app.py", status_code=503)
    with open(path, encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=_WEB_HEADERS)


@app.get("/developers", response_class=HTMLResponse)
def developers_page():
    """API keys + quick start (web_app/developers.html). Uses the web app's sign-in (same site)."""
    path = os.path.join(WEB_APP_DIR, "developers.html")
    with open(path, encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=_WEB_HEADERS)


def _renderer():
    try:
        from .markdown_render import render_markdown_body
    except ImportError:                       # Docker: modules sit side by side
        from markdown_render import render_markdown_body
    return render_markdown_body


@app.post("/render")
def render_markdown(request: Request, data: dict = Body(...)):
    """Markdown -> safe HTML with the app's own formatter (raw HTML and javascript:
    links are neutralised). {"markdown": "..."} or {"items": ["...", ...]} (max 200)."""
    _email_from_auth(request)
    render = _renderer()
    if isinstance(data.get("items"), list):
        items = [str(x or "")[:100_000] for x in data["items"][:200]]
        return {"html": [render(x) for x in items]}
    return {"html": render(str(data.get("markdown") or "")[:100_000])}



# =====================================================================
# Gink Developer API -- OpenAI-compatible, so the official OpenAI libraries work:
#     base_url = "https://<server>/v1",  api_key = "gink_live_..."
#   POST /v1/chat/completions   GET /v1/models   POST /v1/images/generations
# Keys: created / listed / revoked by the signed-in user (/account/api-keys);
# shown once, stored only as a SHA-256 fingerprint. API calls share the account's
# daily allowance (same plan rules as the app) + a per-key per-minute limit.
# =====================================================================
_API_KEYS_TABLE = ("CREATE TABLE IF NOT EXISTS api_keys (id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT,"
                   " key_hash TEXT UNIQUE NOT NULL, hint TEXT, created REAL, last_used REAL,"
                   " requests INTEGER DEFAULT 0, revoked INTEGER DEFAULT 0)")
API_KEY_PREFIX = "gink_live_"
API_MAX_KEYS = 10
API_PER_MINUTE = int(os.environ.get("GINK_API_PER_MINUTE", "30"))
_api_recent = {}                                    # key id -> recent request times (per-minute limit)


def _keys_db():
    con = _db()
    con.execute(_API_KEYS_TABLE)
    return con


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _api_error(status: int, message: str, code: str, headers: dict = None):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status, headers=headers or {},
                        content={"error": {"message": message, "type": "invalid_request_error" if status < 500 else "server_error",
                                           "code": code}})


def _api_key_owner(request: Request):
    """(email, key_id) for a valid, unrevoked key, or an error response."""
    auth = request.headers.get("authorization", "")
    key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not key.startswith(API_KEY_PREFIX):
        return None, _api_error(401, "Missing or invalid API key. Create one on the Developers page.", "invalid_api_key")
    with _db_lock:
        con = _keys_db()
        try:
            row = con.execute("SELECT id, email FROM api_keys WHERE key_hash=? AND revoked=0", (_key_hash(key),)).fetchone()
            if row:
                con.execute("UPDATE api_keys SET last_used=?, requests=requests+1 WHERE id=?", (time.time(), row[0]))
                con.commit()
        finally:
            con.close()
    if not row:
        return None, _api_error(401, "This API key is invalid or was revoked.", "invalid_api_key")
    now = time.time()
    recent = [t for t in _api_recent.get(row[0], []) if now - t < 60]
    if len(recent) >= API_PER_MINUTE:
        wait = int(60 - (now - recent[0])) + 1
        return None, _api_error(429, f"Too many requests: {API_PER_MINUTE} per minute per key. Try again in {wait} s.",
                                "rate_limit", {"Retry-After": str(wait)})
    _api_recent[row[0]] = recent + [now]
    return (row[1], row[0]), None


@app.post("/v1/chat/completions")
async def api_chat(request: Request):
    owner, err = _api_key_owner(request)
    if err:
        return err
    request.state.gink_api_email = owner[0]
    return await ai_chat(request)


@app.get("/v1/models")
async def api_models(request: Request):
    owner, err = _api_key_owner(request)
    if err:
        return err
    live = await _live_groq_models()
    chat = sorted(m for m in (live or set(TEXT_MODELS_BEST_FIRST))
                  if not any(x in m for x in ("whisper", "tts", "guard", "embed", "orpheus", "compound", "allam", "playai")))
    chat += sorted(await _live_claude_models())
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "gink"} for m in chat]}


@app.post("/v1/images/generations")
async def api_images(request: Request):
    """OpenAI-style: {"prompt": "..."} -> {"created", "data": [{"b64_json": "..."}]}."""
    owner, err = _api_key_owner(request)
    if err:
        return err
    request.state.gink_api_email = owner[0]
    result = await media_image(request)
    if not isinstance(result, dict):
        return result                                  # an error response, already explained
    return {"created": int(time.time()), "data": [{"b64_json": result["image_b64"]}],
            "mime_type": result.get("mime_type", "image/png")}


# ---- key management (signed in with the app / web app session) ----
@app.get("/account/api-keys")
def api_keys_list(request: Request):
    email = _email_from_auth(request)
    with _db_lock:
        con = _keys_db()
        try:
            rows = con.execute("SELECT id, name, hint, created, last_used, requests FROM api_keys"
                               " WHERE email=? AND revoked=0 ORDER BY created DESC", (email,)).fetchall()
        finally:
            con.close()
    return {"keys": [{"id": r[0], "name": r[1], "hint": r[2], "created": r[3], "last_used": r[4], "requests": r[5]}
                     for r in rows], "per_minute": API_PER_MINUTE}


@app.post("/account/api-keys")
def api_keys_create(request: Request, data: dict = Body(default={})):
    email = _email_from_auth(request)
    name = " ".join(str((data or {}).get("name") or "My key").split())[:60] or "My key"
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key_id = secrets.token_hex(8)
    with _db_lock:
        con = _keys_db()
        try:
            n = con.execute("SELECT COUNT(*) FROM api_keys WHERE email=? AND revoked=0", (email,)).fetchone()[0]
            if n >= API_MAX_KEYS:
                raise HTTPException(status_code=400, detail=f"You can have up to {API_MAX_KEYS} keys. Revoke one first.")
            con.execute("INSERT INTO api_keys (id, email, name, key_hash, hint, created) VALUES (?, ?, ?, ?, ?, ?)",
                        (key_id, email, name, _key_hash(key), key[:14] + "\u2026" + key[-4:], time.time()))
            con.commit()
        finally:
            con.close()
    return {"id": key_id, "name": name, "key": key, "note": "Copy this key now: it won't be shown again."}


@app.delete("/account/api-keys/{key_id}")
def api_keys_revoke(key_id: str, request: Request):
    email = _email_from_auth(request)
    with _db_lock:
        con = _keys_db()
        try:
            n = con.execute("UPDATE api_keys SET revoked=1 WHERE id=? AND email=? AND revoked=0", (key_id, email)).rowcount
            con.commit()
        finally:
            con.close()
    if not n:
        raise HTTPException(status_code=404, detail="That key doesn't exist.")
    _api_recent.pop(key_id, None)
    return {"revoked": key_id}



# ---- Owner only: give an existing account Gink Pro (testing, gifts, support).
#   POST /admin/grant-pro  header x-admin-key: <GINK_ADMIN_KEY>  {"email": "...", "days": 30}
# Adds the days to the end of any current Pro time, like a payment. tools/grant_pro.py calls it.
@app.post("/admin/grant-pro")
def admin_grant_pro(request: Request, data: dict = Body(...)):
    key = _env("GINK_ADMIN_KEY")
    if len(key) < 24:
        raise HTTPException(status_code=403, detail="Set GINK_ADMIN_KEY on the server (at least 24 random characters).")
    if not hmac.compare_digest(request.headers.get("x-admin-key", ""), key):
        raise HTTPException(status_code=403, detail="Owner only.")
    email = str(data.get("email") or "").strip().lower()
    try:
        days = int(data.get("days") or 30)
    except (TypeError, ValueError):
        days = 0
    if not 1 <= days <= 366:
        raise HTTPException(status_code=422, detail="Days must be between 1 and 366.")
    with _db_lock:
        con = _billing_db()
        try:
            row = con.execute("SELECT pro_until FROM users WHERE email=?", (email,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No account with that email on this server.")
            until = max(time.time(), row[0] or 0) + days * 86400
            con.execute("UPDATE users SET pro_until=? WHERE email=?", (until, email))
            con.commit()
        finally:
            con.close()
    print(f"[Gink] ADMIN: gave {email} {days} days of Gink Pro (until {time.strftime('%Y-%m-%d', time.gmtime(until))})", flush=True)
    return {"email": email, "pro_until": until, "pro_until_date": time.strftime("%Y-%m-%d", time.gmtime(until))}



# ---- Gink on the web: reading attached documents (PDF, Word, text, code...) with the
# desktop app's own reader (services/attachments.py). Photos stay in the browser.
@app.post("/attachments/read")
def attachments_read(request: Request, data: dict = Body(...)):
    _email_from_auth(request)
    try:
        from .attachments import load_data_url, AttachmentError
    except ImportError:                                   # Docker: modules side by side
        from attachments import load_data_url, AttachmentError
    name = str(data.get("name") or "file")[:200]
    url = str(data.get("data") or "")
    if not url.startswith("data:") or len(url) > 28_000_000:
        raise HTTPException(status_code=422, detail="That file is empty or over 20 MB.")
    try:
        att = load_data_url(url, name)
    except AttachmentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=422, detail=f"Gink can't read {name}.")
    if att.kind != "text":
        raise HTTPException(status_code=422, detail="Send photos straight from the chat.")
    return {"name": att.name, "kind": "text", "text": att.text, "note": att.chip().get("note", "")}
