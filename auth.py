"""
OSCAAR auth — drop-in module folded into the existing FastAPI app.

Storage: a single SQLite file (WAL mode). No separate database service.
Adds: users, email_verifications, login_events, query_history.

Design decisions baked in (see project notes):
- Hard gate: the RAG UI and /query are unreachable without a valid session.
- Demo account: fixed username "demo", password read LIVE from OSCAAR_DEMO_PASSWORD
  at login time (never stored, never hashed in the DB). Blank/unset => demo disabled.
  Demo is pre-verified and is the deliberate exception to email verification.
- audience_type (medical|patient) and response_language (en|es) live on the user
  row and are read at query time to switch the synthesis prompt + answer language.
- argon2 hashing. Sessions are signed cookies (no server-side session store needed).

This module exposes:
- init_auth(app)        -> registers routes + startup; call once from query_api.py
- require_user          -> FastAPI dependency; returns the logged-in User or 401/403
- current_user          -> like require_user but returns None instead of raising
- log_query(user, ...)  -> write a row to query_history (call from /query)
"""
import os
import sqlite3
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, HTTPException, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# ─────────────────────────── config (env-driven) ───────────────────────────
DB_PATH        = os.environ.get("OSCAAR_DB_PATH", "/mnt/oscaar/oscaar.db")
SECRET_KEY     = os.environ.get("OSCAAR_SECRET_KEY", "")
BASE_URL       = os.environ.get("OSCAAR_BASE_URL", "https://oscaar.org")
SESSION_HOURS  = int(os.environ.get("OSCAAR_SESSION_HOURS", "168"))   # 7 days
VERIFY_HOURS   = int(os.environ.get("OSCAAR_VERIFY_TOKEN_HOURS", "24"))

DEMO_USERNAME  = "demo"
DEMO_PASSWORD  = os.environ.get("OSCAAR_DEMO_PASSWORD", "")           # blank => disabled

SENDGRID_KEY   = os.environ.get("SENDGRID_API_KEY", "")
EMAIL_FROM     = os.environ.get("OSCAAR_EMAIL_FROM", "noreply@oscaar.org")
EMAIL_FROM_NM  = os.environ.get("OSCAAR_EMAIL_FROM_NAME", "OSCAAR")
EMAIL_DRY_RUN  = (os.environ.get("OSCAAR_EMAIL_DRY_RUN", "").lower() in ("1","true","yes")) or not SENDGRID_KEY

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", f"{BASE_URL}/auth/google/callback")
GOOGLE_ENABLED       = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

SUPPORTED_LANGUAGES = {"en": "English", "es": "Español"}
AUDIENCE_TYPES      = {"medical": "Clinician / researcher", "patient": "Patient / caregiver"}
DEFAULT_LANGUAGE    = "en"

SESSION_COOKIE = "oscaar_session"
COOKIE_SECURE  = not BASE_URL.startswith("http://localhost")

if not SECRET_KEY:
    # Fail loud rather than run with a guessable session signer.
    SECRET_KEY = "INSECURE-DEV-KEY-set-OSCAAR_SECRET_KEY"
    print("WARNING: OSCAAR_SECRET_KEY not set — using an insecure dev key.")

_ph = PasswordHasher()
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="oscaar-session")


# ─────────────────────────── database (SQLite + WAL) ────────────────────────
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")     # readers don't block the writer
    conn.execute("PRAGMA busy_timeout=5000;")    # wait, don't fail, on contention
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id              TEXT PRIMARY KEY,
        email           TEXT UNIQUE NOT NULL,
        password_hash   TEXT,
        auth_provider   TEXT NOT NULL DEFAULT 'local',
        google_sub      TEXT UNIQUE,
        email_verified  INTEGER NOT NULL DEFAULT 0,
        audience_type   TEXT NOT NULL DEFAULT 'patient',
        response_language TEXT NOT NULL DEFAULT 'en',
        welcomed        INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL,
        last_login_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS email_verifications (
        token       TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at  TEXT NOT NULL,
        used        INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS login_events (
        id           TEXT PRIMARY KEY,
        user_id      TEXT REFERENCES users(id) ON DELETE CASCADE,
        timestamp    TEXT NOT NULL,
        ip           TEXT,
        country_code TEXT
    );
    CREATE TABLE IF NOT EXISTS query_history (
        id           TEXT PRIMARY KEY,
        user_id      TEXT REFERENCES users(id) ON DELETE SET NULL,
        is_demo      INTEGER NOT NULL DEFAULT 0,
        question     TEXT NOT NULL,
        audience_type TEXT,
        language     TEXT,
        tokens_total INTEGER,
        timestamp    TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_login_user_time ON login_events(user_id, timestamp);
    CREATE INDEX IF NOT EXISTS ix_qh_user_time   ON query_history(user_id, timestamp);
    CREATE INDEX IF NOT EXISTS ix_qh_time        ON query_history(timestamp);
    """)
    # Migration: add 'welcomed' to pre-existing databases that lack it.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "welcomed" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN welcomed INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


# ─────────────────────────── small helpers ─────────────────────────────────
def _now() -> str:
    return datetime.utcnow().isoformat()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, pw_hash: str) -> bool:
    if not pw_hash:
        return False
    try:
        return _ph.verify(pw_hash, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_ok(pw: str) -> tuple[bool, str]:
    if len(pw) < 10:
        return False, "Use at least 10 characters."
    if pw.isdigit() or pw.isalpha():
        return False, "Mix letters and numbers."
    return True, ""


def issue_session(user_id: str) -> str:
    return _serializer.dumps({"uid": str(user_id)})


def read_session(cookie: str):
    if not cookie:
        return None
    try:
        return _serializer.loads(cookie, max_age=SESSION_HOURS * 3600).get("uid")
    except (BadSignature, SignatureExpired):
        return None


def _client_ip(request: Request):
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _set_session_cookie(resp, user_id: str):
    resp.set_cookie(
        SESSION_COOKIE, issue_session(user_id),
        max_age=SESSION_HOURS * 3600, httponly=True,
        samesite="lax", secure=COOKIE_SECURE,
    )


# ─────────────────────────── user lookups ──────────────────────────────────
class SessionUser:
    """Lightweight user object handed to routes. For demo, id is the sentinel 'demo'."""
    def __init__(self, row=None, is_demo=False):
        self.is_demo = is_demo
        if is_demo:
            self.id = "demo"
            self.email = "demo@oscaar.org"
            self.audience_type = "patient"
            self.response_language = DEFAULT_LANGUAGE
            self.email_verified = True
            self.auth_provider = "demo"
        else:
            self.id = row["id"]
            self.email = row["email"]
            self.audience_type = row["audience_type"]
            self.response_language = row["response_language"]
            self.email_verified = bool(row["email_verified"])
            self.auth_provider = row["auth_provider"]


def _get_user_row(conn, user_id: str):
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def current_user(request: Request):
    """Returns a SessionUser or None. Never raises."""
    uid = read_session(request.cookies.get(SESSION_COOKIE, ""))
    if not uid:
        return None
    if uid == "demo":
        # Demo session only valid while a demo password is configured.
        return SessionUser(is_demo=True) if DEMO_PASSWORD else None
    conn = _connect()
    try:
        row = _get_user_row(conn, uid)
        return SessionUser(row=row) if row else None
    finally:
        conn.close()


def require_user(request: Request):
    """FastAPI dependency: the hard gate. 401 if not logged in, 403 if unverified."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in.")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email not verified.")
    return user


# ─────────────────────────── query history ─────────────────────────────────
def log_query(user, question: str, tokens_total: int):
    """Call from /query after a successful answer. Best-effort; never breaks a query."""
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO query_history "
            "(id, user_id, is_demo, question, audience_type, language, tokens_total, timestamp) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()),
             None if user.is_demo else user.id,
             1 if user.is_demo else 0,
             question[:2000], user.audience_type, user.response_language,
             tokens_total, _now())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[query_history] log failed (non-fatal): {e}")


# ─────────────────────────── email (SendGrid + dry-run) ────────────────────
def _send_email(to_email, subject, html, text) -> bool:
    """Returns True if the email was sent (or dry-run printed), False on failure.
    Never raises — callers decide what to surface to the user."""
    if EMAIL_DRY_RUN:
        print("=" * 70, f"\n[EMAIL DRY RUN] to={to_email}\nsubject: {subject}\n{text}\n", "=" * 70, flush=True)
        return True
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        msg = Mail(from_email=(EMAIL_FROM, EMAIL_FROM_NM), to_emails=to_email,
                   subject=subject, plain_text_content=text, html_content=html)
        resp = SendGridAPIClient(SENDGRID_KEY).send(msg)
        # SendGrid returns 2xx on accept. Anything else is a failure we should know about.
        if 200 <= resp.status_code < 300:
            return True
        print(f"[email] SendGrid returned {resp.status_code} for {to_email}", flush=True)
        return False
    except Exception as e:
        print(f"[email] send failed for {to_email}: {e}", flush=True)
        return False


def _send_verification(to_email, token) -> bool:
    link = f"{BASE_URL}/auth/verify?token={token}"
    return _send_email(
        to_email, "Verify your OSCAAR account",
        f'<div style="font-family:system-ui,sans-serif;max-width:480px;margin:auto">'
        f'<h2 style="color:#1e6fff">Welcome to OSCAAR</h2><p>Confirm your email to activate your account.</p>'
        f'<p><a href="{link}" style="display:inline-block;padding:12px 20px;background:#1e6fff;color:#fff;'
        f'border-radius:8px;text-decoration:none">Verify email</a></p>'
        f'<p style="color:#667;font-size:13px">Link expires in {VERIFY_HOURS} hours.</p></div>',
        f"Welcome to OSCAAR.\nConfirm your email: {link}\nExpires in {VERIFY_HOURS} hours.",
    )


def _welcome_paragraphs(audience_type: str):
    """Returns (subject, [paragraphs]) for the welcome email, flavored by audience."""
    if audience_type == "medical":
        subject = "Welcome to OSCAAR"
        paras = [
            "Hello, and welcome to OSCAAR.",
            "Roughly 18 to 20 people die from cancer every minute worldwide. That startling "
            "number is why OSCAAR was created \u2014 to put vetted cancer literature within "
            "direct reach of the people working against it.",
            "OSCAAR stands for Open Source Cancer Analysis and Research: a growing, curated "
            "repository of cancer literature. Every answer is cited inline \u2014 author, "
            "journal, year, and PMID \u2014 so every claim is traceable to its source. Answers "
            "are drawn solely from peer-reviewed literature, never from the open web.",
            "OSCAAR is not a keyword search engine. It uses natural language processing, so you "
            "can pose a clinical or research question in plain language \u2014 as you would to a "
            "colleague \u2014 rather than constructing query syntax, and it answers directly from "
            "the retrieved literature.",
            "It\u2019s also language-independent. Ask \u201CHow frequent is cancer in children?\u201D "
            "in English, \u201CWie h\u00e4ufig ist Krebs bei Kindern?\u201D in German, or "
            "\u201C兒童癌症的發生率有多高？\u201D "
            "in Chinese \u2014 OSCAAR understands them all, and responds in the language of your question.",
            "So go ahead \u2014 pose your first question, in your own words and your own language. "
            "Welcome to OSCAAR, and thank you for being part of the search for answers.",
        ]
    else:
        subject = "Welcome to OSCAAR"
        paras = [
            "Hello, and welcome to OSCAAR.",
            "Roughly 18 to 20 people die from cancer every minute worldwide. That startling number "
            "is why OSCAAR was created \u2014 to help people find real answers, drawn straight from the science.",
            "OSCAAR stands for Open Source Cancer Analysis and Research. It\u2019s a growing, carefully "
            "curated library of cancer literature. Every answer you get is cited, so you always know "
            "where it came from. Answers are drawn only from vetted, peer-reviewed research \u2014 never "
            "from the open web.",
            "One thing to know: OSCAAR isn\u2019t a search engine. You don\u2019t need special keywords "
            "or medical terms. Just ask your question the way you\u2019d ask a person, in plain, everyday "
            "language, and OSCAAR will answer you directly from the literature.",
            "You can also ask in your own language. \u201CHow common is cancer in children?\u201D in "
            "English, \u201CWie h\u00e4ufig ist Krebs bei Kindern?\u201D in German, or "
            "\u201C兒童癌症的發生率有多高？\u201D in "
            "Chinese \u2014 OSCAAR understands them all, and will answer in the language you asked.",
            "So go ahead \u2014 ask your first question, in your own words and your own language. Welcome "
            "to OSCAAR, and thank you for being part of the search for answers.",
        ]
    return subject, paras


def _send_welcome(to_email, audience_type: str = "patient") -> bool:
    subject, paras = _welcome_paragraphs(audience_type)
    body_html = "".join(
        f'<p style="margin:0 0 14px;line-height:1.6;color:#1a2744;font-size:15px">{p}</p>'
        for p in paras
    )
    html = (
        '<div style="font-family:system-ui,-apple-system,sans-serif;max-width:540px;margin:auto;'
        'padding:8px 4px">'
        '<div style="font-family:Georgia,serif;font-size:22px;font-weight:600;letter-spacing:1px;'
        'color:#1e6fff;margin-bottom:4px">OSCAAR</div>'
        '<div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#7d93ab;'
        'margin-bottom:22px">Open Source Cancer Analysis and Research</div>'
        + body_html +
        '<hr style="border:none;border-top:1px solid #e0e8f0;margin:22px 0 12px">'
        '<p style="font-size:12px;color:#7d93ab;margin:0;line-height:1.5">'
        'All responses are generated from peer-reviewed literature. '
        'Not a substitute for clinical judgment.</p>'
        '</div>'
    )
    text = "\n\n".join(paras)
    return _send_email(to_email, subject, html, text)


def _issue_verification_token(conn, user_id: str) -> str:
    """Create and store a fresh verification token for a user. Returns the token."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(hours=VERIFY_HOURS)).isoformat()
    conn.execute("INSERT INTO email_verifications (token,user_id,expires_at) VALUES (?,?,?)",
                 (token, user_id, expires))
    return token


# ─────────────────────────── routes ────────────────────────────────────────
def init_auth(app):
    """Register all auth routes and the DB startup hook on the given FastAPI app."""

    @app.on_event("startup")
    def _auth_startup():
        init_db()
        print(f"[auth] SQLite ready at {DB_PATH}; demo {'ENABLED' if DEMO_PASSWORD else 'disabled'}; "
              f"Google {'enabled' if GOOGLE_ENABLED else 'disabled'}; "
              f"email {'dry-run' if EMAIL_DRY_RUN else 'SendGrid'}")

    @app.get("/auth/config")
    def auth_config():
        return {
            "google_enabled": GOOGLE_ENABLED,
            "languages": SUPPORTED_LANGUAGES,
            "audience_types": AUDIENCE_TYPES,
            "demo_enabled": bool(DEMO_PASSWORD),
        }

    @app.post("/auth/signup")
    def signup(request: Request,
               email: str = Form(...), password: str = Form(...),
               audience_type: str = Form("patient"), response_language: str = Form("en")):
        email = email.strip().lower()
        if audience_type not in AUDIENCE_TYPES:
            raise HTTPException(400, "Invalid account type.")
        if response_language not in SUPPORTED_LANGUAGES:
            response_language = DEFAULT_LANGUAGE
        ok, msg = password_ok(password)
        if not ok:
            raise HTTPException(400, msg)

        conn = _connect()
        try:
            if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise HTTPException(409, "An account with that email already exists.")
            uid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users (id,email,password_hash,auth_provider,email_verified,"
                "audience_type,response_language,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (uid, email, hash_password(password), "local", 0,
                 audience_type, response_language, _now())
            )
            token = _issue_verification_token(conn, uid)
            conn.commit()
        finally:
            conn.close()

        sent = _send_verification(email, token)
        if not sent:
            # Account exists but the email didn't go out. Tell the user plainly and
            # point them at resend, rather than leaving them stuck wondering.
            return JSONResponse(
                {"ok": True, "email_sent": False,
                 "message": "Your account was created, but we couldn't send the "
                            "verification email just now. Use \u201cResend verification\u201d "
                            "below, or try again in a few minutes."},
            )
        return JSONResponse({"ok": True, "email_sent": True,
                             "message": "Account created. Check your email to verify."})

    @app.post("/auth/resend-verification")
    def resend_verification(email: str = Form(...)):
        """Re-send a verification link. Always responds the same way regardless of
        whether the account exists or is already verified, to avoid leaking which
        emails are registered."""
        email = email.strip().lower()
        generic = JSONResponse(
            {"ok": True,
             "message": "If that email needs verification, a new link is on its way. "
                        "Check your inbox (and spam folder)."}
        )
        conn = _connect()
        try:
            row = conn.execute("SELECT id, email_verified FROM users WHERE email=?", (email,)).fetchone()
            if not row or row["email_verified"]:
                return generic  # nothing to do, but don't reveal that
            # Invalidate any old unused tokens, then issue a fresh one.
            conn.execute("UPDATE email_verifications SET used=1 WHERE user_id=? AND used=0", (row["id"],))
            token = _issue_verification_token(conn, row["id"])
            conn.commit()
        finally:
            conn.close()
        _send_verification(email, token)  # best-effort; response stays generic
        return generic

    @app.get("/auth/verify")
    def verify(token: str):
        conn = _connect()
        try:
            rec = conn.execute("SELECT * FROM email_verifications WHERE token=?", (token,)).fetchone()
            if not rec or rec["used"] or datetime.fromisoformat(rec["expires_at"]) < datetime.utcnow():
                return HTMLResponse("<h3>This verification link is invalid or expired.</h3>", status_code=400)
            user_id = rec["user_id"]
            conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
            conn.execute("UPDATE email_verifications SET used=1 WHERE token=?", (token,))
            email_row = conn.execute("SELECT email, audience_type FROM users WHERE id=?", (user_id,)).fetchone()
            conn.commit()
        finally:
            conn.close()
        if email_row:
            _send_welcome(email_row["email"], email_row["audience_type"])
        # Auto-login: the verification link is proof of identity (only the account
        # owner received this email), so log them in and drop them straight into the
        # app — no need to re-enter credentials on a login screen.
        resp = RedirectResponse("/", status_code=303)
        _set_session_cookie(resp, user_id)
        return resp

    @app.post("/auth/login")
    def login(request: Request, email: str = Form(...), password: str = Form(...)):
        ident = email.strip().lower()

        # Demo path: fixed username, password from env, checked live.
        if ident == DEMO_USERNAME:
            if not DEMO_PASSWORD:
                raise HTTPException(403, "The demo is not currently available.")
            if not secrets.compare_digest(password, DEMO_PASSWORD):
                raise HTTPException(401, "Incorrect demo password.")
            ip = _client_ip(request)
            conn = _connect()
            try:
                conn.execute("INSERT INTO login_events (id,user_id,timestamp,ip,country_code) VALUES (?,?,?,?,?)",
                             (str(uuid.uuid4()), None, _now(), ip, None))
                conn.commit()
            finally:
                conn.close()
            resp = JSONResponse({"ok": True, "redirect": "/"})
            _set_session_cookie(resp, "demo")
            return resp

        # Normal user path.
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE email=?", (ident,)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise HTTPException(401, "Incorrect email or password.")
            if not row["email_verified"]:
                raise HTTPException(403, "Please verify your email before signing in.")
            conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (_now(), row["id"]))
            conn.execute("INSERT INTO login_events (id,user_id,timestamp,ip,country_code) VALUES (?,?,?,?,?)",
                         (str(uuid.uuid4()), row["id"], _now(), _client_ip(request), None))
            conn.commit()
            uid = row["id"]
        finally:
            conn.close()
        resp = JSONResponse({"ok": True, "redirect": "/"})
        _set_session_cookie(resp, uid)
        return resp

    @app.post("/auth/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @app.get("/auth/me")
    def me(request: Request):
        user = current_user(request)
        if not user:
            return {"authenticated": False}
        return {
            "authenticated": True, "email": user.email,
            "audience_type": user.audience_type, "response_language": user.response_language,
            "is_demo": user.is_demo,
        }

    @app.get("/auth/welcome")
    def get_welcome(request: Request):
        """Returns the one-time welcome text and whether to show it.
        Demo sessions never see it. Real users see it once, ever."""
        user = current_user(request)
        if not user:
            return {"show": False}
        if user.is_demo:
            return {"show": False}
        conn = _connect()
        try:
            row = conn.execute("SELECT welcomed FROM users WHERE id=?", (user.id,)).fetchone()
        finally:
            conn.close()
        if not row or row["welcomed"]:
            return {"show": False}
        _, paras = _welcome_paragraphs(user.audience_type)
        return {"show": True, "title": "Welcome to OSCAAR", "paragraphs": paras}

    @app.post("/auth/welcome/dismiss")
    def dismiss_welcome(request: Request):
        """Mark the welcome as seen so it never shows again."""
        user = current_user(request)
        if user and not user.is_demo:
            conn = _connect()
            try:
                conn.execute("UPDATE users SET welcomed=1 WHERE id=?", (user.id,))
                conn.commit()
            finally:
                conn.close()
        return {"ok": True}

    # ── Google OAuth ──
    @app.get("/auth/google/login")
    def google_login():
        if not GOOGLE_ENABLED:
            raise HTTPException(404, "Google login is not configured.")
        from urllib.parse import urlencode
        params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": GOOGLE_REDIRECT_URI,
                  "response_type": "code", "scope": "openid email profile",
                  "access_type": "online", "prompt": "select_account"}
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))

    @app.get("/auth/google/callback")
    def google_callback(code: str, request: Request):
        if not GOOGLE_ENABLED:
            raise HTTPException(404, "Google login is not configured.")
        import httpx
        tok = httpx.post("https://oauth2.googleapis.com/token", timeout=15, data={
            "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI, "grant_type": "authorization_code"}).json()
        access = tok.get("access_token")
        if not access:
            raise HTTPException(400, "Google authorization failed.")
        info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=15,
                         headers={"Authorization": f"Bearer {access}"}).json()
        sub, gmail = info.get("sub"), (info.get("email") or "").lower()
        if not sub or not gmail:
            raise HTTPException(400, "Google profile was incomplete.")

        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE email=?", (gmail,)).fetchone()
            if row:
                if not row["google_sub"]:
                    conn.execute("UPDATE users SET google_sub=?, email_verified=1 WHERE id=?", (sub, row["id"]))
                uid = row["id"]
            else:
                uid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO users (id,email,auth_provider,google_sub,email_verified,"
                    "audience_type,response_language,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (uid, gmail, "google", sub, 1, "patient", DEFAULT_LANGUAGE, _now()))
            conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (_now(), uid))
            conn.execute("INSERT INTO login_events (id,user_id,timestamp,ip,country_code) VALUES (?,?,?,?,?)",
                         (str(uuid.uuid4()), uid, _now(), _client_ip(request), None))
            conn.commit()
        finally:
            conn.close()
        resp = RedirectResponse("/", status_code=303)
        _set_session_cookie(resp, uid)
        return resp
