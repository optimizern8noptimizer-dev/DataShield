"""Flask Web UI and enterprise control plane for DataShield BY 2.3.

Commercial-style single page UI with database upload, masking run, and result
tracking. Optimized for Python 3.15 alpha compatibility by avoiding heavy
compiled web dependencies.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

import yaml
from flask import Flask, Response, jsonify, request, send_file
from sqlalchemy import create_engine, inspect, text
from waitress import serve

from datashield.cache import MemoryCache
from datashield.cli import run_masking_job
from datashield.controlplane import (
    ROLE_ORDER,
    authenticate,
    create_user,
    get_job,
    get_queue_stats,
    get_user_by_token,
    init_db,
    list_audit_events,
    list_jobs,
    list_users,
    record_audit_event,
    record_job,
    revoke_token,
    update_job,
    verify_audit_chain,
)
from datashield.maskers import get_masker, list_services
from datashield.services.validators import validate_pan_luhn, validate_iban_like
from datashield.services.policy_loader import load_policy_profile, list_policy_profiles
from datashield.services.strict_mode import StrictModeSettings, check_unmapped_high_risk, check_production_validation

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["JSON_SORT_KEYS"] = False
app.config["DS_VERSION"] = "2.7.2.1-preview-endpoint-restore"
_cache = MemoryCache()


_SERVICE_DESCRIPTIONS = {
    "basic": "Посимвольное обезличивание",
    "fio": "ФИО, сохраняет класс структуры",
    "birthdate": "Дата рождения, сохраняет возрастную группу",
    "inn": "Legacy tax identifier masker for compatibility",
    "snils": "Legacy personal identifier masker for compatibility",
    "birthplace": "Место рождения / региональный профиль",
    "bankCard": "Номер карты, сохраняет BIN и Luhn",
    "bankCardDefault": "Совместимость: тот же карт-маскер",
    "passport": "Документ личности, совместимый legacy-профиль",
    "drivingLicense": "Водительский документ, совместимый профиль",
    "legalDetails": "Юридическое лицо / ИП",
    "cdiAddress": "Адрес BY-профиль",
    "rawAddress": "Адрес свободного формата",
    "bankAccount": "Банковский счет",
    "phone": "Телефон, по умолчанию +375 профиль",
    "simple_phone": "Телефон без форматных гарантий",
    "email": "Email с заменой домена по типу",
    "vehiclePassport": "Документы ТС",
    "number": "Числовое размытие",
    "identifier": "Идентификатор",
    "taxId": "Налоговый ID",
    "city": "Город",
    "ipAddress": "IP-адрес",
    "deviceId": "Идентификатор устройства",
    "text": "Текстовое поле",
    "cardExpiry": "Срок действия карты",
    "cardHolder": "Держатель карты",
}

_DISCOVERY_PATTERNS = {
    "fio": ["фио", "fullname", "full_name", "fullName", "name", "client_name", "customer_name"],
    "birthdate": ["birth", "birth_date", "dob", "birthday"],
    "phone": ["phone", "mobile", "тел", "msisdn"],
    "email": ["email", "mail", "почта"],
    "bankCard": ["card_number", "pan", "masked_pan", "card_no"],
    "cardExpiry": ["expiry", "exp_date", "expire_date", "expiry_date"],
    "cardHolder": ["holder_name", "cardholder", "card_holder"],
    "bankAccount": ["iban", "account_number", "account_no"],
    "passport": ["passport", "passport_no", "passport_num", "document", "id_doc", "document_number", "personal_number", "identity_number", "id_number"],
    "identifier": ["national_id"],
    "cdiAddress": ["address", "addr", "адрес", "street"],
    "city": ["city", "merchant_city"],
    "legalDetails": ["company", "company_name", "legal", "org", "organization", "taxpayer", "beneficiary_name", "beneficiary_passport"],
    "taxId": ["tax_id", "unp", "okpo", "inn"],
    "region": ["region", "oblast", "область"],
    "datetime": ["created_at", "updated_at", "timestamp", "created", "updated", "event_time", "datetime", "txn_ts"],
    "number": ["amount", "sum", "balance", "salary", "income", "registration_no"],
    "ipAddress": ["ip_address", "src_ip", "client_ip", "remote_ip"],
    "deviceId": ["device_id", "device", "device_guid"],
    "text": ["description", "purpose", "comment", "note", "details"],
}

_ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


def _safe_audit(event_type: str, actor: str, details: dict | str | None = None) -> None:
    try:
        if details is None:
            payload = "{}"
        elif isinstance(details, str):
            payload = details
        else:
            payload = json.dumps(details, ensure_ascii=False)
        record_audit_event(event_type, actor, payload)
    except Exception:
        pass


def _storage_root() -> Path:
    root = Path(os.environ.get("DS_STORAGE_DIR", "./storage")).resolve()
    for sub in (root, root / "uploads", root / "masked", root / "configs", root / "reports"):
        sub.mkdir(parents=True, exist_ok=True)
    return root


def _json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400) -> tuple[Response, int]:
    return jsonify({"detail": message}), status


def _parse_token() -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise PermissionError("Missing Bearer token")
    return authorization.split(" ", 1)[1].strip()


def _require_user() -> dict[str, Any]:
    token = _parse_token()
    legacy = os.environ.get("DATASHIELD_API_TOKEN", "")
    if legacy and token == legacy:
        return {"username": "legacy-token", "role": "admin", "is_active": True}
    user = get_user_by_token(token)
    if not user:
        raise PermissionError("Invalid or expired token")
    return user


def require_role(min_role: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                user = _require_user()
            except PermissionError as exc:
                return _error(str(exc), 401)
            if ROLE_ORDER[user["role"]] < ROLE_ORDER[min_role]:
                return _error(f"Role {min_role} or higher required", 403)
            return fn(user, *args, **kwargs)
        return wrapper
    return decorator


def require_user(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            user = _require_user()
        except PermissionError as exc:
            return _error(str(exc), 401)
        return fn(user, *args, **kwargs)
    return wrapper


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)
    return cleaned[:120] or f"upload_{uuid.uuid4().hex}.sqlite"


def _database_inventory() -> list[dict[str, Any]]:
    root = _storage_root() / "uploads"
    items = []
    files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in _ALLOWED_EXTENSIONS]
    for file in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        upload_id = file.name.split("_", 1)[0]
        items.append({
            "upload_id": upload_id,
            "name": file.name,
            "path": str(file),
            "size_bytes": file.stat().st_size,
            "updated_at": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
        })
    return items




def _sqlite_preview_tables(db_path: Path, limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 100))
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        payload = []
        for table in tables:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]
            rows = con.execute(f'SELECT * FROM "{table}" LIMIT {limit}').fetchall()
            serial_rows = []
            for row in rows:
                item = {}
                for c in cols:
                    val = row[c]
                    item[c] = '' if val is None else str(val)
                serial_rows.append(item)
            row_count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            payload.append({
                "name": table,
                "columns": cols,
                "rows": serial_rows,
                "preview_rows": len(serial_rows),
                "total_rows": int(row_count),
            })
        return {"tables": payload, "limit": limit}
    finally:
        con.close()


def _resolve_uploaded_path(upload_id: str) -> Path | None:
    uploads = _database_inventory()
    match = next((x for x in uploads if x["upload_id"] == upload_id or x["name"].startswith(f"{upload_id}_")), None)
    return Path(match["path"]) if match else None


def _normalize_profile_column_rule(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        return {"service": value}
    if isinstance(value, dict) and value.get("service"):
        rule = {"service": value.get("service")}
        if value.get("linked_columns"):
            rule["linked_columns"] = list(value.get("linked_columns") or [])
        if value.get("params"):
            rule["params"] = dict(value.get("params") or {})
        return rule
    return None


def _profile_table_map(profile_name: str | None) -> dict[str, Any]:
    if not profile_name:
        return {}
    try:
        profile = load_policy_profile(profile_name)
    except Exception:
        return {}
    return profile.get("profiles") or {}


def _profile_metadata(profile_name: str | None) -> dict[str, Any] | None:
    if not profile_name:
        return None
    try:
        profile = load_policy_profile(profile_name)
    except Exception:
        return None
    return {
        "policy_name": profile.get("policy_name", profile_name),
        "policy_version": profile.get("policy_version", "unknown"),
        "country": profile.get("country", "BY"),
        "mode": profile.get("mode", "explicit_profile_first"),
        "strict_policy": profile.get("strict_policy", {}),
    }


def _strict_settings_from_profile(profile_name: str | None, strict_mode: bool) -> StrictModeSettings:
    if not strict_mode:
        return StrictModeSettings(
            fail_on_unmapped_high_risk=False,
            fail_on_pk_change=False,
            fail_on_fk_break=False,
            fail_on_invalid_pan=False,
            fail_on_invalid_iban=False,
        )
    profile = _profile_metadata(profile_name) or {}
    policy = profile.get("strict_policy", {}) if isinstance(profile, dict) else {}
    return StrictModeSettings(
        fail_on_unmapped_high_risk=bool(policy.get("fail_on_unmapped_high_risk", True)),
        fail_on_pk_change=bool(policy.get("fail_on_pk_change", True)),
        fail_on_fk_break=bool(policy.get("fail_on_fk_break", True)),
        fail_on_invalid_pan=bool(policy.get("fail_on_invalid_pan", True)),
        fail_on_invalid_iban=bool(policy.get("fail_on_invalid_iban", True)),
    )


def _discover_table_rules(db_url: str, profile_name: str | None = None, strict_mode: bool = False) -> list[dict[str, Any]]:
    explicit_profiles = _profile_table_map(profile_name)
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    rules: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for table in tables:
            columns = inspector.get_columns(table)
            pk = inspector.get_pk_constraint(table) or {}
            pk_cols = pk.get("constrained_columns") or []
            fks = inspector.get_foreign_keys(table) or []
            fk_source_names = {src.lower() for fk in fks for src in (fk.get("constrained_columns") or [])}
            pk_names = {c.lower() for c in pk_cols}
            col_rules = []
            table_column_names = {c["name"].lower() for c in columns}
            for col in columns:
                cname = col["name"]
                cname_l = cname.lower()
                if cname_l in pk_names or cname_l in fk_source_names or cname_l == "id" or cname_l.endswith("_id"):
                    continue
                service = None
                params: dict[str, Any] = {}

                if service:
                    pass
                elif cname_l == "contact_value" and "contact_type" in table_column_names:
                    service = "dynamicContact"
                    params = {"contact_type_from_column": "contact_type"}
                elif cname_l == "pan":
                    service = "bankCard"
                    linked = []
                    source_columns = {}
                    if "expiry" in table_column_names:
                        linked.append("expiry")
                        source_columns["expiry"] = "expiry"
                    if "holder_name" in table_column_names:
                        linked.append("holder_name")
                        source_columns["holder"] = "holder_name"
                    if linked:
                        params = {"linked_columns": linked, "source_columns": source_columns}
                elif cname_l == "holder_name" and "pan" in table_column_names:
                    service = "cardHolder"
                elif cname_l == "expiry" and "pan" in table_column_names:
                    service = "cardExpiry"
                else:
                    for svc, patterns in _DISCOVERY_PATTERNS.items():
                        if any(pattern.lower() in cname_l for pattern in patterns):
                            service = svc
                            break

                if not service:
                    sample_values = []
                    try:
                        sample_rows = conn.execute(text(f'SELECT "{cname}" FROM "{table}" WHERE "{cname}" IS NOT NULL LIMIT 5')).fetchall()
                        sample_values = [str(r[0]) for r in sample_rows if r and r[0] is not None]
                    except Exception:
                        sample_values = []
                    if sample_values and all("@" in v for v in sample_values):
                        service = "email"
                    elif sample_values and all(re.search(r"\+?\d", v) for v in sample_values) and any(v.startswith("+375") or "(" in v for v in sample_values):
                        service = "phone"
                    elif sample_values and all(re.fullmatch(r"[A-Z]{2}\d{7,}", re.sub(r"\s+", "", v)) for v in sample_values):
                        service = "passport"
                    elif sample_values and all(re.fullmatch(r"[0-9A-Z]{10,20}", re.sub(r"\s+", "", v), re.IGNORECASE) and any(re.search(r"[A-Z]", v, re.IGNORECASE) for v in sample_values) for v in sample_values):
                        service = "identifier"
                    elif sample_values and all(re.fullmatch(r"BY\d{2}[A-Z]{4}[A-Z0-9]{16}", re.sub(r"\s+", "", v), re.IGNORECASE) for v in sample_values):
                        service = "bankAccount"
                    elif sample_values and all(re.fullmatch(r"\d{13,19}", re.sub(r"\D", "", v)) for v in sample_values):
                        service = "bankCard"
                    elif sample_values and all(re.fullmatch(r"\d{6,16}", re.sub(r"\D", "", v)) for v in sample_values):
                        service = "taxId"
                    elif sample_values and all(re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", v) for v in sample_values):
                        service = "ipAddress"
                    elif sample_values and all(v.lower().startswith("dev-") or re.fullmatch(r"[A-Za-z0-9_-]{8,64}", v) for v in sample_values):
                        service = "deviceId"

                if service:
                    col_rule = {"name": cname, "service": service}
                    linked_columns = params.pop("linked_columns", []) if params else []
                    if linked_columns:
                        col_rule["linked_columns"] = linked_columns
                    if params:
                        col_rule["params"] = params
                    col_rules.append(col_rule)
            if not col_rules:
                continue
            fk_columns = []
            for fk in fks:
                constrained = fk.get("constrained_columns") or []
                referred_cols = fk.get("referred_columns") or []
                referred_table = fk.get("referred_table")
                for src, dst in zip(constrained, referred_cols):
                    fk_columns.append({"name": src, "references": f"{referred_table}.{dst}"})
            count = 0
            try:
                count = int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
            except Exception:
                count = 0
            rules.append({
                "name": table,
                "pk_column": pk_cols[0] if pk_cols else None,
                "fk_columns": fk_columns,
                "row_count": count,
                "columns": col_rules,
            })
    if strict_mode:
        findings = _flatten_detected_columns(rules)
        check_unmapped_high_risk(findings, _strict_settings_from_profile(profile_name, strict_mode))
    return rules




def _classify_risk(service: str) -> str:
    if service in {"bankCard", "bankAccount", "passport", "identifier", "taxId", "cardExpiry", "cardHolder"}:
        return "high"
    if service in {"fio", "birthdate", "phone", "email", "cdiAddress", "legalDetails", "city", "ipAddress", "deviceId", "text"}:
        return "medium"
    if service in {"region", "datetime", "number"}:
        return "low"
    return "unknown"


def _flatten_detected_columns(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in rules:
        for col in table.get("columns", []):
            rows.append({
                "table": table.get("name"),
                "column": col.get("name"),
                "service": col.get("service"),
                "risk": _classify_risk(str(col.get("service", ""))),
                "linked_columns": col.get("linked_columns", []),
                "row_count": table.get("row_count", 0),
            })
    return rows



def _validate_row_counts(source_engine, masked_engine, tables: list[str]) -> dict[str, Any]:
    mismatched: list[str] = []
    details: list[dict[str, Any]] = []
    with source_engine.connect() as src_conn, masked_engine.connect() as msk_conn:
        for tname in tables:
            try:
                src_count = int(src_conn.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar() or 0)
                msk_count = int(msk_conn.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar() or 0)
            except Exception:
                continue
            details.append({"table": tname, "source_rows": src_count, "masked_rows": msk_count, "match": src_count == msk_count})
            if src_count != msk_count:
                mismatched.append(tname)
    return {"checked_tables": len(details), "mismatched_tables": mismatched, "details": details}


def _validate_pk_stability(source_engine, masked_engine, rules: list[dict[str, Any]]) -> dict[str, Any]:
    mismatched: list[str] = []
    details: list[dict[str, Any]] = []
    with source_engine.connect() as src_conn, masked_engine.connect() as msk_conn:
        for table in rules:
            tname = table.get("name")
            pk = table.get("pk_column")
            if not tname or not pk:
                continue
            try:
                src_vals = [str(x[0]) for x in src_conn.execute(text(f'SELECT "{pk}" FROM "{tname}" ORDER BY "{pk}"')).fetchall()]
                msk_vals = [str(x[0]) for x in msk_conn.execute(text(f'SELECT "{pk}" FROM "{tname}" ORDER BY "{pk}"')).fetchall()]
            except Exception:
                continue
            match = src_vals == msk_vals
            details.append({"table": tname, "pk_column": pk, "match": match})
            if not match:
                mismatched.append(tname)
    return {"checked_tables": len(details), "mismatched_tables": mismatched, "details": details}


def _validate_fk_integrity(masked_engine, rules: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with masked_engine.connect() as conn:
        for table in rules:
            tname = table.get("name")
            if not tname:
                continue
            try:
                fk_rows = conn.execute(text(f'PRAGMA foreign_key_list("{tname}")')).fetchall()
            except Exception:
                continue
            for row in fk_rows:
                # PRAGMA foreign_key_list columns: id, seq, table, from, to, ...
                ref_table = row[2]
                from_col = row[3]
                to_col = row[4]
                try:
                    q = text(
                        f'SELECT COUNT(*) FROM "{tname}" c LEFT JOIN "{ref_table}" p '
                        f'ON c."{from_col}" = p."{to_col}" '
                        f'WHERE c."{from_col}" IS NOT NULL AND p."{to_col}" IS NULL'
                    )
                    broken = int(conn.execute(q).scalar() or 0)
                except Exception:
                    continue
                if broken > 0:
                    issues.append({"table": tname, "column": from_col, "ref_table": ref_table, "ref_column": to_col, "broken_rows": broken})
    return {"checked": True, "issues": issues, "issue_count": len(issues)}


def _validate_semantics(masked_engine, rules: list[dict[str, Any]]) -> dict[str, Any]:
    pan_total = pan_valid = 0
    iban_total = iban_valid = 0
    distinct_details: list[dict[str, Any]] = []
    with masked_engine.connect() as conn:
        for table in rules:
            tname = table.get("name")
            for col in table.get("columns", []):
                cname = col.get("name")
                service = str(col.get("service") or "")
                try:
                    vals = [x[0] for x in conn.execute(text(f'SELECT "{cname}" FROM "{tname}"')).fetchall()]
                    distinct_count = int(conn.execute(text(f'SELECT COUNT(DISTINCT "{cname}") FROM "{tname}"')).scalar() or 0)
                except Exception:
                    continue
                distinct_details.append({"table": tname, "column": cname, "service": service, "masked_distinct_count": distinct_count})
                if service in {"bankCard", "cardPan"} or cname.lower() in {"pan", "card_number", "masked_pan", "card_no"}:
                    for v in vals:
                        if v is None:
                            continue
                        pan_total += 1
                        if validate_pan_luhn(str(v)):
                            pan_valid += 1
                if service == "bankAccount" or cname.lower() == "iban":
                    for v in vals:
                        if v is None:
                            continue
                        iban_total += 1
                        if validate_iban_like(str(v)):
                            iban_valid += 1
    return {
        "pan_validation": {"masked_total": pan_total, "masked_valid": pan_valid, "masked_invalid": max(pan_total - pan_valid, 0)},
        "iban_validation": {"masked_total": iban_total, "masked_valid": iban_valid, "masked_invalid": max(iban_total - iban_valid, 0)},
        "distinct_counts": distinct_details,
    }


def _compare_databases(source_db: Path, masked_db: Path, profile_name: str | None = None) -> dict[str, Any]:
    src_rules = _discover_table_rules(f"sqlite:///{source_db.as_posix()}", profile_name=profile_name, strict_mode=False)
    detected = _flatten_detected_columns(src_rules)
    source_engine = create_engine(f"sqlite:///{source_db.as_posix()}")
    masked_engine = create_engine(f"sqlite:///{masked_db.as_posix()}")
    summary = {"detected_columns": len(detected), "changed_columns": 0, "unchanged_columns": 0, "coverage_percent": 0.0}
    per_table: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    with source_engine.connect() as src_conn, masked_engine.connect() as msk_conn:
        for table in src_rules:
            tname = table["name"]
            pk = table.get("pk_column")
            if not pk:
                continue
            changed_count = 0
            unchanged_count = 0
            table_findings = []
            for col in table.get("columns", []):
                cname = col.get("name")
                service = col.get("service")
                linked = col.get("linked_columns", []) or []
                compare_cols = [cname] + [x for x in linked if x != cname]
                changed_any = False
                linked_results = []
                for field in compare_cols:
                    try:
                        src_rows = src_conn.execute(text(f'SELECT "{pk}", "{field}" FROM "{tname}" ORDER BY "{pk}"')).fetchall()
                        msk_rows = msk_conn.execute(text(f'SELECT "{pk}", "{field}" FROM "{tname}" ORDER BY "{pk}"')).fetchall()
                    except Exception:
                        continue
                    src_vals = ["" if r[1] is None else str(r[1]) for r in src_rows]
                    msk_vals = ["" if r[1] is None else str(r[1]) for r in msk_rows]
                    changed_rows = sum(1 for a,b in zip(src_vals, msk_vals) if a != b)
                    total_rows = min(len(src_vals), len(msk_vals))
                    src_distinct = len(set(src_vals))
                    msk_distinct = len(set(msk_vals))
                    if changed_rows > 0:
                        changed_any = True
                    linked_results.append({
                        "column": field,
                        "changed_rows": changed_rows,
                        "total_rows": total_rows,
                        "changed": changed_rows > 0,
                        "sample_before": src_vals[0] if src_vals else "",
                        "sample_after": msk_vals[0] if msk_vals else "",
                        "source_distinct_count": src_distinct,
                        "masked_distinct_count": msk_distinct,
                    })
                if changed_any:
                    changed_count += 1
                    summary["changed_columns"] += 1
                else:
                    unchanged_count += 1
                    summary["unchanged_columns"] += 1
                finding = {
                    "table": tname,
                    "column": cname,
                    "service": service,
                    "risk": _classify_risk(str(service or "")),
                    "status": "changed" if changed_any else "unchanged",
                    "linked_results": linked_results,
                }
                table_findings.append(finding)
                findings.append(finding)
            per_table.append({
                "table": tname,
                "detected_columns": len(table.get("columns", [])),
                "changed_columns": changed_count,
                "unchanged_columns": unchanged_count,
                "coverage_percent": round((changed_count / len(table.get("columns", [])) * 100.0), 2) if table.get("columns") else 0.0,
                "findings": table_findings,
            })
    total = summary["detected_columns"] or 1
    summary["coverage_percent"] = round(summary["changed_columns"] / total * 100.0, 2)
    summary["high_risk_unmasked"] = sum(1 for f in findings if f["status"] == "unchanged" and f["risk"] == "high")
    summary["medium_risk_unmasked"] = sum(1 for f in findings if f["status"] == "unchanged" and f["risk"] == "medium")

    validation = {
        "row_count_check": _validate_row_counts(source_engine, masked_engine, [t.get("name") for t in src_rules if t.get("name")]),
        "pk_stability": _validate_pk_stability(source_engine, masked_engine, src_rules),
        "fk_integrity_check": _validate_fk_integrity(masked_engine, src_rules),
    }
    validation.update(_validate_semantics(masked_engine, src_rules))
    return {"summary": summary, "per_table": per_table, "findings": findings, "validation": validation}


def _safe_scalar(value: Any) -> str:
    if isinstance(value, tuple):
        return "_".join(str(v) for v in value)
    return str(value)


def _safe_join_linked_columns(items: list[dict[str, Any]] | None) -> str:
    values: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            values.append(_safe_scalar(item.get("column", "")))
        else:
            values.append(_safe_scalar(item))
    return ";".join(values)


def _csv_escape(value: Any) -> str:
    return '"' + _safe_scalar(value).replace('"', '""') + '"'


def _write_coverage_report(job_id: str, source_db: Path, masked_db: Path, config_path: Path, profile_name: str | None = None, strict_mode: bool = False) -> tuple[dict[str, Any], Path]:
    report = _compare_databases(source_db, masked_db, profile_name=profile_name)
    report.update({
        "policy_profile": _profile_metadata(profile_name),
        "strict_mode": strict_mode,
        "job_id": job_id,
        "source_db": str(source_db),
        "masked_db": str(masked_db),
        "config_path": str(config_path),
        "generated_at_utc": datetime.utcnow().isoformat(),
    })
    report_path = _storage_root() / "reports" / f"coverage_{job_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = report_path.with_suffix(".csv")
    lines = ["table,column,service,risk,status,linked_columns"]
    for finding in report["findings"]:
        linked = _safe_join_linked_columns(finding.get("linked_results", []))
        vals = [
            _safe_scalar(finding.get("table", "")),
            _safe_scalar(finding.get("column", "")),
            _safe_scalar(finding.get("service", "")),
            _safe_scalar(finding.get("risk", "")),
            _safe_scalar(finding.get("status", "")),
            linked,
        ]
        lines.append(",".join(_csv_escape(v) for v in vals))
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    report["report_json_path"] = str(report_path)
    report["report_csv_path"] = str(csv_path)
    report["download_report_json_url"] = f"/api/reports/download/{report_path.name}"
    report["download_report_csv_url"] = f"/api/reports/download/{csv_path.name}"
    return report, report_path


def _load_report(job_id: str) -> dict[str, Any] | None:
    path = _storage_root() / "reports" / f"coverage_{job_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))

def _write_generated_config(source_db: Path, masked_db: Path, mask_mode: str = "deterministic", profile_name: str | None = None, strict_mode: bool = False) -> tuple[Path, list[dict[str, Any]]]:
    root = _storage_root()
    rules = _discover_table_rules(f"sqlite:///{masked_db.as_posix()}", profile_name=profile_name, strict_mode=strict_mode)
    config = {
        "version": "2.3",
        "session": {
            "mode": "in_place",
            "mask_mode": mask_mode,
            "snapshot_before": False,
            "parallelism": 1,
            "batch_size": 1000,
        },
        "source": {
            "type": "sqlite",
            "database": str(masked_db),
        },
        "tables": [
            {
                "name": t["name"],
                "pk_column": t["pk_column"],
                "fk_columns": t["fk_columns"],
                "columns": t["columns"],
            }
            for t in rules
        ],
        "policy": {
            "profile_name": profile_name,
            "profile_metadata": _profile_metadata(profile_name),
            "strict_mode": strict_mode,
        },
        "audit": {
            "log_path": str(root / "datashield_audit.jsonl"),
            "strict_key": False,
        },
    }
    config_path = root / "configs" / f"mask_job_{masked_db.stem}.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return config_path, rules


@app.get("/api/policy-profiles")
@require_role("operator")
def policy_profiles(user: dict):
    names = list_policy_profiles()
    return jsonify({"profiles": [{"name": n, **(_profile_metadata(n) or {})} for n in names]})


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "version": app.config["DS_VERSION"],
        "timestamp": datetime.utcnow().isoformat(),
        "docs": "/docs",
        "auth_mode": "local+oidc-ready",
        "worker_mode": "external-queue-worker+direct-ui-mask",
        "framework": "flask",
        "python_315_profile": True,
    })


@app.get("/api/auth/providers")
def auth_providers():
    oidc_enabled = bool(os.environ.get("DS_OIDC_ISSUER_URL"))
    return jsonify({
        "local": True,
        "oidc": {
            "enabled": oidc_enabled,
            "issuer": os.environ.get("DS_OIDC_ISSUER_URL", ""),
            "client_id": os.environ.get("DS_OIDC_CLIENT_ID", ""),
            "note": "OIDC bootstrap is configuration-ready; local auth remains default.",
        },
        "ldap": {
            "enabled": False,
            "note": "LDAP is not embedded in v2.3. Use OIDC federation from AD/Keycloak/Entra ID.",
        },
    })


@app.post("/api/auth/login")
def login():
    req = _json_body()
    username = str(req.get("username", "")).strip()
    password = str(req.get("password", "")).strip()
    session = authenticate(username, password)
    if not session:
        return _error("Invalid username or password", 401)
    _safe_audit("login", username, {"result": "success"})
    return jsonify(session)


@app.post("/api/auth/logout")
@require_user
def logout(user: dict):
    token = _parse_token()
    revoke_token(token)
    _safe_audit("logout", user["username"], {})
    return jsonify({"status": "logged_out"})


@app.get("/api/auth/me")
@require_user
def me(user: dict):
    return jsonify(user)


@app.get("/api/services")
@require_user
def services_api(user: dict):
    return jsonify([
        {"name": name, "description": _SERVICE_DESCRIPTIONS.get(name, "")}
        for name in list_services()
    ])


@app.post("/api/mask")
@require_role("operator")
def mask_api(user: dict):
    req = _json_body()
    service = str(req.get("service", ""))
    value = req.get("value")
    mode = str(req.get("mode", "deterministic") or "deterministic")
    profile_name = str(req.get("profile_name", "") or "").strip() or None
    strict_mode = bool(req.get("strict_mode", False))
    params = req.get("params") if isinstance(req.get("params"), dict) else {}
    try:
        masker = get_masker(service, cache=_cache, mode=mode)
        result = masker.mask(value, **params)
        _safe_audit("mask_preview", user["username"], {"service": service})
        return jsonify({"original": value, "masked": result, "service": service})
    except Exception as exc:
        return _error(str(exc), 400)


@app.get("/api/cache/stats")
@require_role("admin")
def cache_stats(user: dict):
    return jsonify(_cache.stats())


@app.get("/api/audit/events")
@require_role("security_officer")
def audit_events(user: dict):
    return jsonify(list_audit_events(200))


@app.get("/api/audit/verify")
@require_role("security_officer")
def audit_verify(user: dict):
    return jsonify({"issues": verify_audit_chain(1000)})


@app.get("/api/users")
@require_role("admin")
def users_api(user: dict):
    return jsonify(list_users())


@app.post("/api/users")
@require_role("admin")
def create_user_api(user: dict):
    req = _json_body()
    try:
        created = create_user(
            username=str(req.get("username", "")),
            password=str(req.get("password", "")),
            role=str(req.get("role", "viewer") or "viewer"),
            is_active=bool(req.get("is_active", True)),
        )
        _safe_audit("user_create", user["username"], {"target": created["username"], "role": created["role"]})
        return jsonify(created)
    except Exception as exc:
        return _error(str(exc), 400)


@app.get("/api/jobs")
@require_user
def jobs_api(user: dict):
    return jsonify(list_jobs(100))


@app.get("/api/queue/stats")
@require_role("operator")
def queue_stats(user: dict):
    return jsonify(get_queue_stats())


@app.post("/api/jobs/run")
@require_role("operator")
def run_job(user: dict):
    req = _json_body()
    cfg_path = Path(str(req.get("config_path", "")))
    if not cfg_path.exists():
        return _error(f"Config not found: {cfg_path}", 404)

    job_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat()
    mode = req.get("mode")
    tables = req.get("tables") if isinstance(req.get("tables"), list) else []
    verbose = bool(req.get("verbose", False))
    record_job(job_id, user["username"], str(cfg_path), mode, json.dumps(tables, ensure_ascii=False), verbose)
    _safe_audit("job_submit", user["username"], {"job_id": job_id, "config_path": str(cfg_path)})
    return jsonify({"job_id": job_id, "status": "queued", "started_at": started_at})


@app.get("/api/jobs/<job_id>")
@require_user
def job_status(user: dict, job_id: str):
    job = get_job(job_id)
    if not job:
        return _error("Job not found", 404)
    return jsonify(job)


@app.get("/api/databases")
@require_role("operator")
def list_databases(user: dict):
    return jsonify(_database_inventory())


@app.post("/api/databases/upload")
@require_role("operator")
def upload_database(user: dict):
    if "file" not in request.files:
        return _error("file is required", 400)
    file = request.files["file"]
    if not file.filename:
        return _error("filename is empty", 400)
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return _error("Only SQLite files are supported in the commercial upload workflow (.db/.sqlite/.sqlite3)", 400)

    upload_id = uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(file.filename)
    dest = _storage_root() / "uploads" / f"{upload_id}_{safe_name}"
    file.save(dest)

    db_url = f"sqlite:///{dest.as_posix()}"
    rules = _discover_table_rules(db_url)
    table_count = len(rules)
    row_count = sum(int(t.get("row_count", 0)) for t in rules)
    response = {
        "upload_id": upload_id,
        "original_name": file.filename,
        "saved_name": dest.name,
        "saved_path": str(dest),
        "db_type": "sqlite",
        "table_count": table_count,
        "detected_rows": row_count,
        "tables": rules,
        "available_policy_profiles": list_policy_profiles(),
        "analysis_summary": {
            "detected_columns": len(_flatten_detected_columns(rules)),
            "high_risk_detected": sum(1 for x in _flatten_detected_columns(rules) if x["risk"] == "high"),
            "medium_risk_detected": sum(1 for x in _flatten_detected_columns(rules) if x["risk"] == "medium"),
        },
    }
    _safe_audit("database_upload", user["username"], {"upload_id": upload_id, "path": str(dest), "tables": table_count})
    return jsonify(response)


@app.post("/api/databases/mask")
@require_role("operator")
def mask_uploaded_database(user: dict):
    req = _json_body()
    upload_id = str(req.get("upload_id", "")).strip()
    mode = str(req.get("mode", "deterministic") or "deterministic")
    profile_name = str(req.get("profile_name", "") or "").strip() or None
    strict_mode = bool(req.get("strict_mode", False))
    if mode not in {"deterministic", "randomized"}:
        return _error("mode must be deterministic or randomized", 400)
    uploads = _database_inventory()
    match = next((x for x in uploads if x["upload_id"] == upload_id or x["name"].startswith(f"{upload_id}_")), None)
    if not match:
        return _error("Uploaded database not found", 404)

    source_path = Path(match["path"])
    result_id = uuid.uuid4().hex[:12]
    masked_path = _storage_root() / "masked" / f"masked_{result_id}_{source_path.name}"
    shutil.copy2(source_path, masked_path)
    config_path, rules = _write_generated_config(source_path, masked_path, mask_mode=mode, profile_name=profile_name, strict_mode=strict_mode)

    job_id = str(uuid.uuid4())
    record_job(job_id, user["username"], str(config_path), "in_place", json.dumps([t["name"] for t in rules], ensure_ascii=False), False)
    update_job(job_id, status="running", worker_name="direct-ui-mask", heartbeat_at=datetime.utcnow())
    try:
        result = run_masking_job(config=str(config_path), mode="in_place", tables=[], verbose=False)
        coverage_report, _report_path = _write_coverage_report(job_id, source_path, masked_path, config_path, profile_name=profile_name, strict_mode=strict_mode)
        if strict_mode:
            check_production_validation(coverage_report, _strict_settings_from_profile(profile_name, strict_mode))
        output = {
            "job_id": job_id,
            "upload_id": upload_id,
            "mode": mode,
            "source_db": str(source_path),
            "masked_db": str(masked_path),
            "config_path": str(config_path),
            "policy_profile": _profile_metadata(profile_name),
            "strict_mode": strict_mode,
            "download_url": f"/api/databases/download/{masked_path.name}",
            "tables_total": len(result.get("tables", [])),
            "rows_total": result.get("total_rows", 0),
            "saved_message": f"Маскированная база сохранена: {masked_path}",
            "coverage_report": coverage_report,
            "result": result,
        }
        update_job(job_id, status="completed", result_json=json.dumps(output, ensure_ascii=False), worker_name="direct-ui-mask", heartbeat_at=datetime.utcnow())
        _safe_audit("database_mask", user["username"], {"job_id": job_id, "upload_id": upload_id, "masked_db": str(masked_path)})
        return jsonify(output)
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc), worker_name="direct-ui-mask", heartbeat_at=datetime.utcnow())
        _safe_audit("database_mask_failed", user["username"], {"job_id": job_id, "upload_id": upload_id, "error": str(exc)})
        return _error(str(exc), 500)




@app.get("/api/reports/<job_id>")
@require_role("operator")
def get_report(user: dict, job_id: str):
    report = _load_report(job_id)
    if not report:
        return _error("Report not found", 404)
    return jsonify(report)


@app.get("/api/reports/download/<filename>")
@require_role("operator")
def download_report(user: dict, filename: str):
    path = (_storage_root() / "reports" / filename).resolve()
    root = (_storage_root() / "reports").resolve()
    if root not in path.parents:
        return _error("Invalid file path", 400)
    if not path.exists():
        return _error("File not found", 404)
    return send_file(path, as_attachment=True, download_name=path.name)




@app.post("/api/databases/source-preview")
@require_role("operator")
def source_preview(user: dict):
    req = _json_body()
    upload_id = str(req.get("upload_id", "")).strip()
    limit = int(req.get("limit", 20) or 20)
    source_path = _resolve_uploaded_path(upload_id)
    if not source_path:
        return _error("Uploaded database not found", 404)
    return jsonify({
        "upload_id": upload_id,
        "source_db": str(source_path),
        **_sqlite_preview_tables(source_path, limit=limit),
    })


@app.post("/api/databases/masked-preview")
@require_role("operator")
def masked_preview(user: dict):
    req = _json_body()
    masked_name = str(req.get("masked_name", "")).strip()
    limit = int(req.get("limit", 20) or 20)
    if not masked_name:
        return _error("masked_name is required", 400)
    path = (_storage_root() / "masked" / masked_name).resolve()
    root = (_storage_root() / "masked").resolve()
    if root not in path.parents:
        return _error("Invalid masked file path", 400)
    if not path.exists():
        return _error("Masked database not found", 404)
    return jsonify({
        "masked_name": masked_name,
        "masked_db": str(path),
        **_sqlite_preview_tables(path, limit=limit),
    })


@app.post("/api/databases/analyze")
@require_role("operator")
def analyze_uploaded_database(user: dict):
    req = _json_body()
    upload_id = str(req.get("upload_id", "")).strip()
    uploads = _database_inventory()
    match = next((x for x in uploads if x["upload_id"] == upload_id or x["name"].startswith(f"{upload_id}_")), None)
    if not match:
        return _error("Uploaded database not found", 404)
    source_path = Path(match["path"])
    profile_name = str(req.get("profile_name", "") or "").strip() or None
    strict_mode = bool(req.get("strict_mode", False))
    rules = _discover_table_rules(f"sqlite:///{source_path.as_posix()}", profile_name=profile_name, strict_mode=strict_mode)
    detected = _flatten_detected_columns(rules)
    response = {
        "upload_id": upload_id,
        "source_db": str(source_path),
        "summary": {
            "tables": len(rules),
            "detected_columns": len(detected),
            "high_risk_detected": sum(1 for x in detected if x["risk"] == "high"),
            "medium_risk_detected": sum(1 for x in detected if x["risk"] == "medium"),
            "low_risk_detected": sum(1 for x in detected if x["risk"] == "low"),
        },
        "tables": rules,
        "detected_columns": detected,
        "policy_profile": _profile_metadata(profile_name),
        "strict_mode": strict_mode,
    }
    _safe_audit("database_analyze", user["username"], {"upload_id": upload_id, "detected_columns": len(detected)})
    return jsonify(response)

@app.get("/api/databases/download/<filename>")
@require_role("operator")
def download_masked_database(user: dict, filename: str):
    path = (_storage_root() / "masked" / filename).resolve()
    masked_root = (_storage_root() / "masked").resolve()
    if masked_root not in path.parents:
        return _error("Invalid file path", 400)
    if not path.exists():
        return _error("File not found", 404)
    return send_file(path, as_attachment=True, download_name=path.name)


@app.get("/")
def ui():
    html = Path(__file__).with_name("ui.html").read_text(encoding="utf-8")
    return Response(html, mimetype="text/html; charset=utf-8")


@app.get("/docs")
def docs():
    routes = [
        {"method": "GET", "path": "/api/health"},
        {"method": "GET", "path": "/api/auth/providers"},
        {"method": "POST", "path": "/api/auth/login"},
        {"method": "POST", "path": "/api/auth/logout"},
        {"method": "GET", "path": "/api/auth/me"},
        {"method": "GET", "path": "/api/services"},
        {"method": "POST", "path": "/api/mask"},
        {"method": "POST", "path": "/api/databases/source-preview"},
        {"method": "POST", "path": "/api/databases/masked-preview"},
        {"method": "GET", "path": "/api/policy-profiles"},
        {"method": "GET", "path": "/api/cache/stats"},
        {"method": "GET", "path": "/api/audit/events"},
        {"method": "GET", "path": "/api/audit/verify"},
        {"method": "GET", "path": "/api/users"},
        {"method": "POST", "path": "/api/users"},
        {"method": "GET", "path": "/api/jobs"},
        {"method": "POST", "path": "/api/jobs/run"},
        {"method": "GET", "path": "/api/jobs/<job_id>"},
        {"method": "GET", "path": "/api/queue/stats"},
        {"method": "GET", "path": "/api/databases"},
        {"method": "POST", "path": "/api/databases/upload"},
        {"method": "POST", "path": "/api/databases/source-preview"},
        {"method": "POST", "path": "/api/databases/masked-preview"},
        {"method": "POST", "path": "/api/databases/analyze"},
        {"method": "POST", "path": "/api/databases/mask"},
        {"method": "GET", "path": "/api/reports/<job_id>"},
        {"method": "GET", "path": "/api/reports/download/<filename>"},
        {"method": "GET", "path": "/api/databases/download/<filename>"},
    ]
    return jsonify({
        "title": "DataShield BY 2.4.4 field mapping profile",
        "framework": "flask",
        "openapi": False,
        "routes": routes,
        "auth": "Bearer token",
    })


# Ensure DB is ready at import time for WSGI and test clients.
init_db()


def main() -> int:
    host = os.environ.get("DS_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DS_WEB_PORT", "8080"))
    threads = int(os.environ.get("DS_WEB_THREADS", "8"))
    serve(app, host=host, port=port, threads=threads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
