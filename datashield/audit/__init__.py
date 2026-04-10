"""Append-only audit log with HMAC signatures."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("datashield.audit")
_DEFAULT_SENTINEL = "datashield-audit-key-change-in-production"


def _get_hmac_key(strict: bool = False) -> bytes:
    value = os.environ.get("DATASHIELD_AUDIT_KEY", _DEFAULT_SENTINEL)
    if strict and value == _DEFAULT_SENTINEL:
        raise RuntimeError("DATASHIELD_AUDIT_KEY is not configured")
    return value.encode("utf-8")


def _sign(data: str, strict: bool = False) -> str:
    return hmac.new(_get_hmac_key(strict=strict), data.encode("utf-8"), hashlib.sha256).hexdigest()


class AuditLog:
    def __init__(self, log_path: str = "datashield_audit.jsonl", strict_key: bool = False):
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._strict_key = strict_key

    def _write(self, entry: dict):
        payload = json.dumps(entry, ensure_ascii=False, default=str)
        signature = _sign(payload, strict=self._strict_key)
        record = json.dumps({"payload": entry, "sig": signature}, ensure_ascii=False, default=str)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(record + "\n")

    def log_session(self, session_id: str, stats: list):
        entry = {
            "event": "session_complete",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "tables": [s.to_dict() if hasattr(s, "to_dict") else s for s in stats],
            "total_rows": sum((s.rows_processed if hasattr(s, "rows_processed") else s.get("rows_processed", 0)) for s in stats),
        }
        self._write(entry)
        logger.info("[Audit] session %s recorded to %s", session_id, self._path)

    def log_event(self, event: str, **kwargs):
        self._write({"event": event, "timestamp": datetime.now().isoformat(), **kwargs})

    def verify(self) -> list[dict]:
        violations = []
        if not self._path.exists():
            return violations
        with open(self._path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                try:
                    record = json.loads(line.strip())
                    payload_str = json.dumps(record["payload"], ensure_ascii=False, default=str)
                    expected = _sign(payload_str, strict=False)
                    if record["sig"] != expected:
                        violations.append({"line": i, "issue": "signature mismatch"})
                except Exception as e:
                    violations.append({"line": i, "issue": str(e)})
        return violations

    def read_sessions(self, limit: int = 50) -> list[dict]:
        if not self._path.exists():
            return []
        sessions = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    sessions.append(json.loads(line.strip())["payload"])
                except Exception:
                    pass
        return sessions[-limit:]
