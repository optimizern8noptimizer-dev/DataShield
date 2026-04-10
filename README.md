Python profile: Windows/Python 3.15 alpha hotfix path using Flask + waitress + SQLite local mode by default.

# DataShield BY 2.2.2 Enterprise py315 Hotfix

Enterprise-oriented fork of the provided DataShield source for anonymization of banking databases with Belarus-oriented defaults, web management, RBAC, queue worker execution and audit hash-chain.

## Included
- Flask Web UI and API
- Waitress WSGI serving for local Windows run
- SQLite control-plane by default for Windows hotfix mode
- Local login/logout and RBAC (`viewer` / `operator` / `security_officer` / `admin`)
- External worker queue (`app` enqueues, `worker` executes)
- Audit hash-chain verification
- OIDC-ready configuration surface (local auth remains default)
- Docker Compose deployment
- Demo SQLite dataset and example config
- Windows bootstrap/start scripts

## Quick start (Windows / Python 3.15)
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_py315.ps1
.\scripts\start_all_windows.cmd
```

Open:
- UI: `http://127.0.0.1:8080`
- Docs: `http://127.0.0.1:8080/docs`

Detailed guides:
- `INSTALL_WINDOWS_PY315.md`
- `INSTALL_PRODUCTION_BY_v2.2.md`


## Windows Python 3.15 note

This package pins SQLAlchemy to the 2.1 series to avoid pulling `greenlet` by default. If you previously attempted installation with an older environment, delete `.venv` and recreate it before running bootstrap again.
