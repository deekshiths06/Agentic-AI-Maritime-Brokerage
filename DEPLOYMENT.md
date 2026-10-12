# Maritime AI - Production Deployment

This guide walks a production deployment of the Maritime Brokerage
platform: the FastAPI backend, its MongoDB database, and the built
frontend served behind a reverse proxy. It mirrors exactly how the
application runs in development so nothing behaves differently in
production.

- Backend: `backend/` (FastAPI + Uvicorn + MongoDB)
- Frontend: `frontend/` (React + Vite, static build)
- Live AIS vessel data: optional (AISHub account)
- Gemini advisory: optional (Google AI Studio key)

---

## 1. What the pieces are

```
Browser
   │  (https://brokerage.example.com)
   ▼
Reverse proxy  (nginx / Caddy)
   ├── /        → frontend/dist (static files)
   └── /api     → http://127.0.0.1:8000  (backend)
                        │
                        ▼
                       Uvicorn (FastAPI app, backend/main.py)
                        │
                        ▼
                       MongoDB
```

The frontend always calls relative `/api/*` URLs, so the reverse
proxy is what connects it to the backend. There is no machine-
specific URL baked into the static build.

---

## 2. Backend environment

Copy the template and set every value.

```bash
cd backend
cp .env.example .env
```

Required in production (the backend refuses to start without them):

| Variable           | Purpose                                                  |
| ------------------ | -------------------------------------------------------- |
| `APP_ENVIRONMENT`  | Any value except `development`/`dev`/`local`/`test`      |
|                    | enables production-strict checks.                        |
| `MONGO_URI`        | MongoDB connection string (hosted or local).             |
| `MONGO_DATABASE`   | Database name (default `maritime_brokerage`).            |
| `JWT_SECRET`       | Long random value. Signs login tokens.                   |
| `ADMIN_EMAIL`      | Seed the initial administrator account.                  |
| `ADMIN_PASSWORD`   | Seed the initial administrator account.                  |

Generate secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Optional but recommended:

| Variable              | Purpose                                          |
| --------------------- | ------------------------------------------------ |
| `CORS_ORIGINS`        | Comma-separated frontend origin(s) allowed to    |
|                       | call the API, e.g. `https://brokerage.example.com`. |
| `AIS_API_KEY`         | Live vessel positions for the Maritime Route Map.|
| `AIS_DEFAULT_BOUNDS`  | Restrict the AIS area to keep payloads small,    |
|                       | e.g. `-40,20,40,110` for the Indian Ocean.       |
| `GEMINI_API_KEY`      | Natural-language customs advisory. The module    |
|                       | works without it (deterministic advisory only).  |

`ALLOW_ALL_ORIGINS=true` is accepted for convenience only; it
disables credentialed requests and must never be used in
production. Never commit a real `.env` file - the repository's
`.gitignore` excludes it.

---

## 3. Run the backend

Install the runtime dependencies and start with Uvicorn:

```bash
cd backend
python -m venv venv
venv\Scripts\activate                  # Windows
# source venv/bin/activate             # macOS / Linux

pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 8000
```

On startup the backend:

1. Seeds the administrator account from `ADMIN_EMAIL` /
   `ADMIN_PASSWORD` if it does not exist (never duplicates it).
2. Creates the MongoDB indexes used by the collections.

Production recommendations:

- Run Uvicorn behind a process manager (systemd / supervisord) so
  it restarts on failure.
- Add `--workers 2` for more concurrency. Because the app stores
  tokens in `localStorage` and never uses sticky sessions, multiple
  workers are safe (Mongo holds the real state; the in-memory
  per-process JWT fallback only matters in `development`).

---

## 4. Build and serve the frontend

```bash
cd frontend
npm install
npm run build        # outputs to frontend/dist
```

Serve `frontend/dist` as the `/` root of the reverse proxy and
forward every `/api` request to the backend.

Example nginx virtual host (paths are examples - adjust to your
layout):

```nginx
server {
    listen 443 ssl;
    server_name brokerage.example.com;

    # TLS certificates (Let's Encrypt via certbot)
    ssl_certificate     /etc/letsencrypt/live/brokerage.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/brokerage.example.com/privkey.pem;

    root /srv/maritime-ai/frontend/dist;
    index index.html;

    # SPA: any non-asset path serves index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

For Vite dev against a remote API instead, copy
`frontend/.env.example` to `frontend/.env` and set
`VITE_API_URL`; `npm run dev` then proxies `/api` there. This is
for development only.

---

## 5. Security checklist

- `JWT_SECRET`, `ADMIN_PASSWORD`, `AIS_API_KEY`, `GEMINI_API_KEY`
  and `MONGO_URI` exist only in the untracked `.env` files.
- `APP_ENVIRONMENT` is set to something other than a development
  value, so the backend refuses to start with a blank secret.
- Only the frontend origins you control are listed in
  `CORS_ORIGINS`.
- MongoDB listen addresses and authentication follow the database
  vendor's hardening guide; the application itself never stores
  plaintext passwords (bcrypt) and never returns a secret in any
  API response.
- The admin area is enforced by the backend (`require_admin` on
  every `/api/admin/*` endpoint). Editing frontend `localStorage`
  cannot grant access to it.

---

## 6. Releasing a new version

1. Backend: `cd backend && venv\Scripts\python.exe -m unittest discover -s tests -v`
2. Frontend: `cd frontend && npm run lint && npm run build`
3. Restart Uvicorn, then re-deploy `frontend/dist` behind the
   proxy. The static files can be swapped with zero backend
   downtime because every `/api` call is stateless.