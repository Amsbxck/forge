# Deployment Guide

This guide deploys IronCoach AI in three parts:

- **Backend + Database** on Railway (FastAPI + Postgres)
- **Frontend** on Vercel (React/Vite)
- **Strava webhook** re-registered to the public Railway URL

Total cost: ~$5/month (Railway). Vercel is free for personal projects.

---

## 0. Mirror GitLab → GitHub

Railway cannot read a GitLab repository. GitLab pushes a copy to GitHub on
every push, and Railway deploys from that copy. You keep working against
GitLab — nothing about the daily workflow changes.

1. On GitHub: create a **private** repository `ironcoach-ai`. Do not
   initialise it with a README — the mirror needs an empty target.
2. GitHub → **Settings → Developer settings → Personal access tokens**:
   create a token with `repo` scope.
3. GitLab → **Settings → Repository → Mirroring repositories**:

```
Git repository URL:  https://<github-user>@github.com/<github-user>/ironcoach-ai.git
Mirror direction:    Push
Password:            <the GitHub token>
```

4. **Mirror now**, then check that `main` and the tags arrived on GitHub.

The mirror is one-way. Anything committed directly on GitHub is overwritten
on the next run — GitLab stays the source.

Nothing is lost in the copy: commits, branches and tags all transfer. Issues,
merge requests, wikis and CI variables live in the platform, not the
repository, and do not come along. This project uses none of them.

**Alternative without a mirror:** deploy with the Railway CLI from GitLab CI
(`railway up`) or push a prebuilt image. More moving parts, but GitLab stays
the only remote.

---

## 1. Backend on Railway

### 1.1 Sign up

**Railway deploys from GitHub, not GitLab.** The source of truth stays on
GitLab; a push mirror keeps a GitHub copy in sync, and Railway watches that.
Set this up first — see §0 below.

1. Go to https://railway.app and sign up with **GitHub**
2. Create a new project → **Deploy from GitHub repo** → pick the mirrored
   `ironcoach-ai`
3. When asked about root directory, set it to **`ironcoach-api`** (Railway will detect the `Dockerfile`)

### 1.2 Add Postgres

1. In the project, click **+ New** → **Database** → **Add PostgreSQL**
2. Railway provisions a managed Postgres instance
3. A new env var `DATABASE_URL` is automatically available to all services in the project

### 1.3 Set environment variables on the backend service

In the Railway service → **Variables** tab, add:

```
ANTHROPIC_API_KEY=sk-ant-...
STRAVA_CLIENT_ID=<your strava id>
STRAVA_CLIENT_SECRET=<your strava secret>
STRAVA_VERIFY_TOKEN=<any random string>
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=50

# REQUIRED — the app refuses to start without it.
# Without a fixed secret every restart invalidates all logins, and on Railway
# a restart happens on every deploy. Generate one and never change it again:
#   openssl rand -hex 32
JWT_SECRET=<64 hex characters>

# REQUIRED — where the frontend is served from. The browser blocks every
# request from any origin not listed here, silently, with an error that only
# shows up in the developer console. Comma-separated, no trailing slash.
CORS_ORIGINS=https://your-frontend.vercel.app
```

`DATABASE_URL` is set automatically — don't override it.

`PORT` is set by Railway and picked up by the container. `WEB_CONCURRENCY`
controls the number of worker processes; leave it at 1 on a small instance —
more processes share the same core and get slower, not faster.

Optional: a welcome email on registration. Leave these out and registration
still works — the send is skipped and logged.

```
MAIL_HOST=smtp.your-provider.com
MAIL_PORT=587
MAIL_USER=coach@your-domain.com
MAIL_PASSWORD=<smtp password>
MAIL_FROM=coach@your-domain.com
MAIL_FROM_NAME=IronCoach
MAIL_STARTTLS=true          # port 587; for port 465 use MAIL_SSL=true instead

# Required as soon as MAIL_HOST is set — the app refuses to start otherwise.
# Verification and password-reset links are built from this. Without it they
# point at localhost: the mail arrives, the link is useless, and nobody
# notices until someone cannot sign in.
PUBLIC_BASE_URL=https://your-frontend.vercel.app
```

### 1.4 Add a volume for uploaded .fit files

Railway services have ephemeral filesystems by default. Add a volume:

1. Service settings → **Volumes** → **+ New Volume**
2. Mount path: `/app/uploads`
3. Size: 1 GB is plenty for `.fit` files

### 1.5 Deploy

Railway builds the Dockerfile and runs Alembic migrations + uvicorn on boot (see the `CMD` in `ironcoach-api/Dockerfile`). After ~2 minutes you get a public URL like `https://ironcoach-api-production-xxxx.up.railway.app`.

Test it: `https://<your-url>/docs` should show the FastAPI Swagger UI.

### 1.6 Back up the database

There is no automatic backup. Set one up before anyone else uses the app —
a lost season is not recoverable from anywhere else.

```bash
# From your machine, against the deployed database:
DATABASE_URL="postgresql://..." ./scripts/backup.sh

# Restore (asks for confirmation, and backs up the current state first):
DATABASE_URL="postgresql://..." ./scripts/restore.sh backups/ironcoach_<date>.sql.gz
```

Copy the connection string from Railway → Postgres service → **Connect**.
`scripts/backup.sh` keeps the 14 most recent dumps and refuses to delete old
ones if the new dump is empty or corrupt — a failed run must never take the
last working backup with it.

Run it on a schedule (cron on your machine, or a Railway cron service):

```
0 3 * * *  cd /path/to/IronCoach-AI && DATABASE_URL="postgresql://..." ./scripts/backup.sh
```

**Test the restore once, before you need it.** Restore into a scratch
database and compare the row counts:

```bash
psql "$DATABASE_URL" -c "CREATE DATABASE restore_probe;"
gunzip -c backups/ironcoach_<date>.sql.gz | psql "<...>/restore_probe"
psql "<...>/restore_probe" -c "SELECT count(*) FROM training_sessions;"
psql "$DATABASE_URL" -c "DROP DATABASE restore_probe;"
```


---

## 2. Frontend on Vercel

### 2.1 Sign up & import

1. Go to https://vercel.com, sign up with GitLab
2. **Add New Project** → pick `laxerju/ironcoach-ai`
3. Configure:
   - **Root Directory:** `ironcoach-frontend`
   - **Framework Preset:** Vite (auto-detected)
   - **Build Command:** `npm run build` (default)
   - **Output Directory:** `dist` (default)

### 2.2 Environment variable

Add one env var:

```
VITE_API_URL=https://<your-railway-backend-url>
```

(no trailing slash)

This makes the Axios client in `src/services/api.js` point at Railway instead of using a relative path (which only worked behind the Docker Compose proxy).

### 2.3 Deploy

Click **Deploy**. After ~1 minute you get `https://ironcoach-ai.vercel.app` (or similar).

### 2.4 (Optional) Custom domain

In Vercel: **Settings → Domains** → add your domain. Vercel handles TLS automatically.

---

## 3. Re-register Strava webhook

Strava webhooks need to point to your public Railway URL.

### 3.1 Update `register_webhook.py`

Edit the script (or run with env vars):

```bash
export STRAVA_CLIENT_ID=...
export STRAVA_CLIENT_SECRET=...
export STRAVA_VERIFY_TOKEN=...   # same value you set in Railway
export CALLBACK_URL=https://<your-railway-url>/webhook

python register_webhook.py
```

Strava sends a `GET /webhook?hub.verify_token=...` to confirm — the backend handles it in `routers/strava_webhook.py`.

### 3.2 (Optional) Delete old webhook first

If you already registered a localhost/ngrok webhook earlier, list and delete it:

```bash
curl -X GET https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=$STRAVA_CLIENT_ID \
  -F client_secret=$STRAVA_CLIENT_SECRET

# returns [{ "id": 12345, ... }]

curl -X DELETE "https://www.strava.com/api/v3/push_subscriptions/12345" \
  -F client_id=$STRAVA_CLIENT_ID \
  -F client_secret=$STRAVA_CLIENT_SECRET
```

---

## 4. Obsidian over Tailscale (one vault per athlete)

Obsidian's Local REST API runs on the athlete's own machine, on their home
network. A server on Railway cannot reach it — no port forwarding, no public
address. Tailscale closes that gap: it builds a private network that the
server and every athlete's machine both sit on.

The app already stores the vault address **per athlete** (Profile →
Connections), so each person points at their own vault. What follows is the
network part.

### 4.1 Put the server on the tailnet

1. Tailscale admin → **Settings → Keys** → generate a **reusable, ephemeral**
   auth key. Ephemeral means the node disappears when the container stops,
   so redeploys don't leave dead entries behind.
2. Railway → backend service → Variables: `TS_AUTHKEY=tskey-auth-...`
3. The container needs `tailscaled` in userspace mode. Railway has no
   `/dev/net/tun`, so the normal kernel mode will not work:

```dockerfile
RUN apt-get update && apt-get install -y curl &&     curl -fsSL https://tailscale.com/install.sh | sh
# then, before uvicorn:
#   tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &
#   tailscale up --authkey="$TS_AUTHKEY" --hostname=ironcoach-api
```

Userspace mode means outgoing connections go through the SOCKS5 proxy — the
HTTP client needs `ALL_PROXY=socks5://localhost:1055` for requests to reach
the tailnet.

### 4.2 Each athlete joins

Per person, once:

1. Install Tailscale and sign in.
2. Expose the Obsidian plugin over the tailnet with a real certificate:

```bash
tailscale serve --bg --https=27124 https://127.0.0.1:27124
tailscale status            # shows the machine name
```

3. In the app: **Profile → Connections → Obsidian**, enter
   `https://<machine>.<tailnet>.ts.net:27124` and the API key from the
   Obsidian plugin.

`tailscale serve` gives the address a Let's Encrypt certificate, so
`OBSIDIAN_VERIFY_TLS=true` becomes possible. Without it the plugin's
self-signed certificate forces `false`.

### 4.3 Restrict what the server can reach

Everyone on a tailnet can reach everyone else by default. That is more than
this needs. In the Tailscale admin → **Access Controls**, restrict the server
to the one port it uses, and keep athletes from reaching each other:

```json
{
  "tagOwners": { "tag:ironcoach": ["autogroup:admin"] },
  "acls": [
    { "action": "accept", "src": ["tag:ironcoach"],
      "dst": ["autogroup:member:27124"] }
  ]
}
```

Tag the server node with `tag:ironcoach` when it joins
(`tailscale up --advertise-tags=tag:ironcoach`).

### 4.4 What this does not solve

- **The machine has to be on.** A closed laptop syncs nothing. The sessions
  are not lost — they sync on the next successful run — but the vault lags.
- **Tailscale's free plan has a user limit.** Check the current number before
  inviting people. An alternative is node sharing: each athlete stays in their
  own tailnet and shares only the one machine with yours.
- **The Obsidian API key is stored in plain text** in `athlete_profile`. It
  grants access to that vault. For a private circle that is a deliberate
  trade-off, not an oversight — but it is worth knowing.


---

## 5. First-time setup

1. Open `https://ironcoach-ai.vercel.app`
2. Go to **Profile** → fill in FTP, max HR, race date, plan start date
3. (Optional) Click **Connect Strava** to authorize
4. Log your first HRV in the Dashboard
5. Generate your first plan in **Weekly Plan**

---

## CI/CD

Both platforms auto-deploy on every push:

- **Vercel** → push to default branch redeploys the frontend
- **Railway** → push to default branch rebuilds the backend container

For preview branches:
- Vercel makes a preview URL per PR/branch automatically
- Railway can do the same if enabled in service settings

---

## Cost breakdown

| Service | Free tier | Pay-as-you-go |
|---------|-----------|---------------|
| Vercel | 100GB bandwidth, hobby plan | Free for personal use |
| Railway | $5 credit/month | ~$5/month for small Postgres + small backend |
| Anthropic API | – | Pay per token (plan generation: ~10-20 cents each) |
| Strava API | Free for personal | – |

Total: **~$5/month** + API costs.

---

## Troubleshooting

**Plan generation times out on Vercel**
The frontend `generatePlan` has a 180s timeout (see `src/services/api.js`). Railway has no platform timeout for HTTP — should work. If you still see timeouts, check Railway logs.

**Webhook not firing**
Verify the URL Strava has: `curl GET /api/v3/push_subscriptions` (auth as in §3.2). Make sure the URL ends in `/webhook` and uses HTTPS.

**Uploads disappear after redeploy**
You forgot the volume in step 1.4. Add it, restart the service.

**Frontend says "Network Error"**
Check `VITE_API_URL` is set in Vercel and matches your Railway URL exactly. No trailing slash.
