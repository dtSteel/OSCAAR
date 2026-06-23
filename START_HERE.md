# OSCAAR Login — Complete File Set

This is everything for the whole login system: username/password login, signup,
email verification, **resend verification**, the rotating demo account, Google
login, and audience/language-aware answers. Storage is one SQLite file — no
Postgres, no separate database service.

There are 5 files. Two are NEW, three REPLACE files you already have.
**Back up the three you're replacing before you copy these in.**

---

## Where each file goes

All five live in **`/mnt/oscaar/`** — the same directory your app already runs
from (where the current `query_api.py` and `index.html` are).

| File | Action | Goes here |
|---|---|---|
| `auth.py` | **NEW** — drop it in | `/mnt/oscaar/auth.py` |
| `query_api.py` | **REPLACE** your current one | `/mnt/oscaar/query_api.py` |
| `index.html` | **REPLACE** your current one | `/mnt/oscaar/index.html` |
| `login.html` | **NEW** — drop it in | `/mnt/oscaar/login.html` |
| `MERGE_RUNBOOK.md` | reference only (not served) | keep wherever you like |

So after copying, `/mnt/oscaar/` contains (among your existing files):
```
/mnt/oscaar/
├── query_api.py     ← replaced
├── auth.py          ← new
├── index.html       ← replaced
├── login.html       ← new
├── oscaar.db        ← created automatically on first run (don't make this yourself)
└── pubmed_env/      ← your existing venv, unchanged
```

---

## Install steps (Option A — FastAPI serves everything)

### 1. Back up what you're replacing
```bash
cd /mnt/oscaar
cp query_api.py query_api.py.bak
cp index.html index.html.bak
```

### 2. Copy the 5 files into /mnt/oscaar/
(Use whatever you normally use — scp, MobaXterm, git pull once these are in GitHub.)

### 3. Install the new Python packages into your existing venv
```bash
/mnt/oscaar/pubmed_env/bin/pip install argon2-cffi itsdangerous "pydantic[email]" python-multipart sendgrid httpx
```

### 4. Add settings to /etc/oscaar-api.env
Generate a secret key:
```bash
/mnt/oscaar/pubmed_env/bin/python -c "import secrets;print(secrets.token_urlsafe(48))"
```
Then append to `/etc/oscaar-api.env` (keep your existing `OPENAI_API_KEY` line):
```ini
OSCAAR_SECRET_KEY=<paste the generated key>
OSCAAR_DB_PATH=/mnt/oscaar/oscaar.db
OSCAAR_BASE_URL=https://oscaar.org
OSCAAR_FRONTEND_DIR=/mnt/oscaar
OSCAAR_DEMO_PASSWORD=<the password you give at demos; blank = demo disabled>

# Email — you've done full domain authentication, so just add the key:
SENDGRID_API_KEY=<your real SendGrid key>
OSCAAR_EMAIL_FROM=noreply@oscaar.org
OSCAAR_EMAIL_FROM_NAME=OSCAAR

# Google login (optional — leave blank to hide the button):
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

### 5. Point nginx's root at the API, then test + reload
Your nginx currently sends `/` to the static server on :8081 and `/api/` to :8000.
Change the root to go to :8000 too (FastAPI now serves the UI). Working shape:
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/;     # trailing slash strips /api/
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location / {
    proxy_pass http://127.0.0.1:8000;       # no trailing slash; preserves path
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```
```bash
sudo nginx -t && sudo systemctl reload nginx
```
(If `nginx -t` fails, it does NOT reload — your live site stays up. Fix and retry.)

### 6. Restart the API and confirm email is in SEND mode
```bash
sudo systemctl restart oscaar-api
journalctl -u oscaar-api -n 20 --no-pager | grep -i auth
```
You want to see `email SendGrid` in that line — NOT `email dry-run`. If it says
dry-run, the SendGrid key didn't load (typo, or a stray OSCAAR_EMAIL_DRY_RUN=true).

### 7. Test in a browser
- https://oscaar.org → redirects to the login screen.
- `demo` + your demo password → lands in the app, can query.
- Create a real account with an outside email (e.g. Gmail) → verification email
  arrives in the INBOX → click link → "Email verified" → sign in.
- (Optional) Try signing in before clicking the link → you'll see "verify your
  email" plus a **Resend verification email** link.

### 8. Once login works, retire the old static server
```bash
sudo systemctl disable --now oscaar-web
```

---

## Rotating the demo password on the road
```bash
sudo nano /etc/oscaar-api.env       # edit OSCAAR_DEMO_PASSWORD=...
sudo systemctl restart oscaar-api
```
Blank it and restart to close the demo door entirely between trips.

---

## What the resend / email-failure handling does
- If SendGrid fails during signup, the account is still created and the user is
  told plainly that the email didn't send and to use "Resend verification."
  (Old behavior would have failed silently.) The failure is logged:
  `[email] send failed for <addr>: <reason>` — visible in `journalctl -u oscaar-api`.
- `/auth/resend-verification` issues a fresh link and invalidates the old one.
- For privacy it always replies the same way ("if that email needs verification,
  a link is on its way") whether or not the account exists or is already verified,
  so it can't be used to discover which emails are registered.

---

## Counts & history (SQLite)
```bash
sqlite3 /mnt/oscaar/oscaar.db
```
```sql
SELECT substr(timestamp,1,10) day, count(*) FROM query_history GROUP BY day ORDER BY day DESC;
SELECT is_demo, count(*) FROM query_history GROUP BY is_demo;
SELECT u.email, count(*) n FROM query_history q JOIN users u ON u.id=q.user_id GROUP BY u.email ORDER BY n DESC;
```

## Backups (do this — accounts can't be regenerated)
```bash
sqlite3 /mnt/oscaar/oscaar.db ".backup '/mnt/oscaar/oscaar-$(date +%F).db'"
```

## Rollback (everything reverses)
```bash
cd /mnt/oscaar
cp query_api.py.bak query_api.py
cp index.html.bak index.html
sudo systemctl restart oscaar-api
sudo systemctl enable --now oscaar-web          # if you'd retired it
sudo nginx -t && sudo systemctl reload nginx    # if you'd changed nginx
```
