Python profile: tested as a pure-Python install path for Python 3.15 alpha; PostgreSQL driver remains optional extra.

# DataShield BY 2.0 - installation and use

## 1. Purpose
DataShield BY 2.0 anonymizes banking datasets for DEV, UAT and analytics use-cases with Web-based control and audit logging.

## 2. Minimum requirements
- Python 3.10+
- PostgreSQL / MariaDB / Oracle / SQLite source supported through SQLAlchemy
- Optional Redis for shared deterministic cache

## 3. Installation
### 3.1 Linux / macOS
```bash
cd datashield
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### 3.2 Windows PowerShell
```powershell
cd datashield
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

## 4. Environment variables
### Linux / macOS
```bash
export DATASHIELD_API_TOKEN=__REPLACE_ME_STRONG_TOKEN__
export DATASHIELD_AUDIT_KEY=__REPLACE_ME_MIN_32_CHARS__
```

### Windows PowerShell
```powershell
$env:DATASHIELD_API_TOKEN="__REPLACE_ME_STRONG_TOKEN__"
$env:DATASHIELD_AUDIT_KEY="__REPLACE_ME_MIN_32_CHARS__"
```

## 5. Start Web UI
```bash
datashield-web
```
Open browser:
- URL: `http://127.0.0.1:8080`
- Field: `API token`
- Paste: value from `DATASHIELD_API_TOKEN`
- Click: `Save token`

## 6. Health check
```bash
curl http://127.0.0.1:8080/api/health
```
Expected: JSON with `status: ok` and version.

## 7. Single-value masking from CLI
```bash
datashield mask -s fio -v "Иванов Пётр Сергеевич"
datashield mask -s phone -v "+375 (29) 123-45-67"
datashield mask -s bankCard -v "4111111111111111"
```

## 8. Dry-run masking from YAML
Config path:
- `config/example_config.yaml`

Run:
```bash
datashield run --config config/example_config.yaml --mode dry_run
```

## 9. Web console features
Path: `http://127.0.0.1:8080`
- `Dashboard` - service overview and cache stats
- `Mask test` - test any value through API
- `Run job` - launch config-based anonymization
- `Sessions` - recent audit sessions
- `Services` - supported masking services

## 10. Example API calls
### 10.1 Mask one value
```bash
curl -X POST http://127.0.0.1:8080/api/mask   -H "Authorization: Bearer __REPLACE_ME_STRONG_TOKEN__"   -H "Content-Type: application/json"   -d '{"service":"email","value":"client@example.com","mode":"deterministic"}'
```

### 10.2 Run job from config
```bash
curl -X POST http://127.0.0.1:8080/api/jobs/run   -H "Authorization: Bearer __REPLACE_ME_STRONG_TOKEN__"   -H "Content-Type: application/json"   -d '{"config_path":"config/example_config.yaml","mode":"dry_run"}'
```

## 11. What to replace
- `__REPLACE_ME_STRONG_TOKEN__` - long random API token
- `__REPLACE_ME_MIN_32_CHARS__` - audit HMAC key, minimum 32 random characters

## 12. Troubleshooting
### Symptom
`401 Unauthorized`
### Cause
Missing or wrong `Authorization: Bearer ...` token.
### Fix
Set `DATASHIELD_API_TOKEN`, restart server, paste same token in UI.

### Symptom
`Audit key is not configured`
### Cause
`DATASHIELD_AUDIT_KEY` missing in strict mode.
### Fix
Set environment variable and restart.

### Symptom
`Unsafe where_clause`
### Cause
Config contains unsupported SQL filter syntax.
### Fix
Use only simple safe filters, e.g. `is_active = true`, `status = 'ACTIVE'`, `created_at >= '2025-01-01'`.
