Python profile: tested as a pure-Python install path for Python 3.15 alpha; PostgreSQL driver remains optional extra.

# DataShield BY 2.2.1 Enterprise py315 — Production Install Guide

## 1. Prerequisites
- Docker Engine 24+
- Docker Compose plugin
- Free TCP port `8080`

## 2. Files to edit
Path:
- `./.env`

Create the file:
```bash
cp .env.example .env
```

Replace:
- `DS_BOOTSTRAP_PASSWORD`
- `DATASHIELD_AUDIT_KEY`
- optionally `DS_OIDC_ISSUER_URL`
- optionally `DS_OIDC_CLIENT_ID`

## 3. Start the stack
Path:
- terminal in project root

Command:
```bash
docker compose up -d --build
```

Services:
- `postgres` — control-plane DB
- `redis` — auxiliary cache/message backend placeholder
- `migrate` — schema bootstrap
- `app` — Web/API
- `worker` — queue executor

## 4. Open the UI
Path:
- browser → `http://127.0.0.1:8080`

Default login:
- username = value of `DS_BOOTSTRAP_ADMIN`
- password = value of `DS_BOOTSTRAP_PASSWORD`

## 5. Queue a job
UI path:
- `Job enqueue`
- field `config path` = `config/example_config.yaml`
- click `Queue job`
- open `List jobs`
- open `Queue stats`

The job is executed by the separate `worker` service.

## 6. API checks
- `GET /api/health`
- `GET /api/auth/providers`
- `GET /api/queue/stats`
- `GET /api/audit/verify`

Swagger path:
- `http://127.0.0.1:8080/docs`

## 7. Security notes
- local auth is active by default
- OIDC in v2.2 is configuration-ready only; use external IdP federation
- audit events are chained with `prev_hash` → `event_hash`
- worker execution is separated from the web process

## Errors
### Symptom
`401 Invalid or expired token`
### Cause
Login was not performed or token expired.
### Fix
Re-login through UI or `POST /api/auth/login`.

### Symptom
Jobs stay in `queued`
### Cause
Worker container is not running.
### Fix
Check:
```bash
docker compose ps
```
Then restart:
```bash
docker compose up -d worker
```

### Symptom
`DATASHIELD_AUDIT_KEY is not configured`
### Cause
Strict audit mode enabled in config without a key.
### Fix
Set `DATASHIELD_AUDIT_KEY` in `.env`.

## Verification
Success criteria:
1. `docker compose ps` shows `app` and `worker` as running.
2. `/api/health` returns version `2.2.0`.
3. queued jobs move to `running` and then `completed`.
4. `/api/audit/verify` returns an empty `issues` array.
