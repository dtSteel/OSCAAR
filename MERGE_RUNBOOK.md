# OSCAAR Auth Merge — Runbook

This folds username/password login (plus a rotating demo account, Google login,
email verification, and audience/language-aware answers) into your existing live
app. Storage is a single SQLite file — no Postgres, no separate database service.

You're choosing between two deployment shapes. **Option A is built and recommended.**
Option B notes are at the bottom for completeness.

---

## What changed (4 files)

| File | Status | What it is |
|---|---|---|
| `auth.py` | **NEW** | The whole auth module: SQLite tables, sessions, login/signup/verify/Google routes, demo logic, query logging. Drop it next to `query_api.py`. |
| `query_api.py` | **MODIFIED** | Imports `auth`, gates `/query` behind login, switches the system prompt by audience+language, logs each query, serves the frontend. See `query_api.diff`. |
| `index.html` | **MODIFIED** | Sends the session cookie with requests, bounces to `/login` on 401, adds a "signed in as / Sign out" header control. See `index.diff`. |
| `login.html` | **NEW** | The login/signup screen, matched to OSCAAR's palette and logo. |

`query_api.diff` and `index.diff` are unified diffs — read them to see exactly
what was touched before you apply anything.

---

## Option A — FastAPI serves everything (RECOMMENDED, what's built)

The single FastAPI app (oscaar-api) now serves the login page, the query UI, and
the API. The static server (oscaar-web on :8081) is no longer needed and retires.
This is the only shape that gives a true hard gate — there's no second door on
:8081 serving the UI unauthenticated.

### Step 1 — place the files
Put all four files in `/mnt/oscaar` (alongside the existing `query_api.py`):
```
/mnt/oscaar/query_api.py     (replace — back up the old one first)
/mnt/oscaar/auth.py          (new)
/mnt/oscaar/index.html       (replace — back up first)
/mnt/oscaar/login.html       (new)
```
Back up first:
```bash
cd /mnt/oscaar
cp query_api.py query_api.py.bak
cp index.html index.html.bak
```

### Step 2 — install the new Python deps into the existing venv
```bash
/mnt/oscaar/pubmed_env/bin/pip install argon2-cffi itsdangerous "pydantic[email]" python-multipart sendgrid httpx
```
(fastapi/uvicorn/openai are already there.)

### Step 3 — add settings to /etc/oscaar-api.env
Append these. Generate a real secret key once and paste it in:
```bash
# print a key to paste:
/mnt/oscaar/pubmed_env/bin/python -c "import secrets;print(secrets.token_urlsafe(48))"
```
```ini
OSCAAR_SECRET_KEY=<paste the generated key>
OSCAAR_DB_PATH=/mnt/oscaar/oscaar.db
OSCAAR_BASE_URL=https://oscaar.org
OSCAAR_FRONTEND_DIR=/mnt/oscaar
OSCAAR_DEMO_PASSWORD=<the password you'll give at demos; blank disables demo>
# email (optional now — blank = console dry-run, verification links print to the log):
SENDGRID_API_KEY=<your SendGrid key, or leave blank for now>
OSCAAR_EMAIL_FROM=noreply@oscaar.org
# Google login (optional — leave blank to hide the button):
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```
`OPENAI_API_KEY` stays as it is.

### Step 4 — nginx: route everything to the API
Today nginx sends `/api/` to :8000 and the root to :8081. Now the root must also
go to :8000 (FastAPI serves the UI). Edit the oscaar.org server block so the API
backend serves all paths. The key change is the location that currently proxies
`/` to `127.0.0.1:8081` should proxy to `127.0.0.1:8000`, and the `/api/` block
should keep stripping the prefix. A working shape:

```nginx
# Strip /api/ and forward to the FastAPI backend
location /api/ {
    proxy_pass http://127.0.0.1:8000/;     # trailing slash strips /api/
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Everything else (login page, query UI, /auth/*, /health) -> FastAPI
location / {
    proxy_pass http://127.0.0.1:8000;       # NO trailing slash; preserves path
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

IMPORTANT: the `/auth/*` routes are served at the ROOT (e.g. `/auth/login`), not
under `/api/`. The login page calls them at `/auth/...` directly, which the
`location /` block above handles. The query UI keeps calling `/api/query` and
`/api/examples` as before. Both work with this config.

Test and reload (never skip the test):
```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Step 5 — restart the API, retire the web server
```bash
sudo systemctl restart oscaar-api
# confirm it came up and the DB initialized:
journalctl -u oscaar-api -n 30 --no-pager | grep -i auth

# once you've confirmed login works in a browser, retire the static server:
sudo systemctl disable --now oscaar-web
```

### Step 6 — verify in a browser
- Visit https://oscaar.org → should redirect to the login screen.
- Log in as `demo` + your `OSCAAR_DEMO_PASSWORD` → lands on the query UI.
- Run a query → works, and gets the patient-friendly wording.
- Sign out → back to login.
- (If email is configured) create a real account → verification email arrives →
  click link → sign in → answers come back in clinician tone (and Spanish if chosen).

### Rotating the demo password on the road
```bash
sudo nano /etc/oscaar-api.env     # change OSCAAR_DEMO_PASSWORD=...
sudo systemctl restart oscaar-api
```
Set it blank and restart to close the demo door entirely between trips.

---

## Counts & history (what you asked for)

Every answered query writes a row to `query_history`. Examples you can run any time:
```bash
sqlite3 /mnt/oscaar/oscaar.db
```
```sql
-- total queries per day
SELECT substr(timestamp,1,10) AS day, count(*) FROM query_history GROUP BY day ORDER BY day DESC;
-- demo vs real usage
SELECT is_demo, count(*) FROM query_history GROUP BY is_demo;
-- most active accounts
SELECT u.email, count(*) AS n FROM query_history q JOIN users u ON u.id=q.user_id
  GROUP BY u.email ORDER BY n DESC LIMIT 20;
-- total accounts, verified vs not
SELECT email_verified, count(*) FROM users GROUP BY email_verified;
```

---

## Backups (do this — accounts can't be regenerated)
A daily cron copying the SQLite file is enough:
```bash
# consistent online backup (safe while the app runs)
sqlite3 /mnt/oscaar/oscaar.db ".backup '/mnt/oscaar/backups/oscaar-$(date +\%F).db'"
```

---

## Option B — keep both services, gate only the API

If you'd rather not touch nginx's root routing yet: keep oscaar-web serving the
static files on :8081, and rely on the fact that `/query` now returns 401 without
a session. The frontend already redirects to `/login` on 401.

Trade-off (why A is better): with B, the UI page itself is still served by the
dumb static server, so someone hitting :8081 directly sees the interface (they
just can't run a query). It's not a true hard gate, and the login page would also
need to be served by the static server. For a chaperoned demo it's tolerable, but
A is cleaner and what's built/tested here. To do B you'd skip retiring oscaar-web,
keep the nginx root pointing at :8081, and copy login.html into the static dir —
ask and I'll write the B-specific variant.

---

## Rollback
Everything is reversible:
```bash
cd /mnt/oscaar
cp query_api.py.bak query_api.py
cp index.html.bak index.html
sudo systemctl restart oscaar-api
sudo systemctl enable --now oscaar-web     # if you'd retired it
sudo nginx -t && sudo systemctl reload nginx   # if you'd changed nginx
```

---

## Notes carried over from planning
- The `demo` account is pre-verified and the deliberate exception to email
  verification. It's chaperoned, so no rate-limiting is built in.
- Recommended regardless: give the demo its own OpenAI project/key with a budget
  cap so demo traffic can never exhaust the production key. (Set a second key and
  swap it in for demo sessions later if you want this — not wired in yet.)
- `audience_type = "medical"` is a TONE preference, not a verified credential.
  If you ever gate *content* behind it, add real verification separately.
- Country-per-login is left as a column but not populated (no GeoIP wired in yet);
  when you add it, store country code, not raw IP, and add a privacy line to the ToS.
