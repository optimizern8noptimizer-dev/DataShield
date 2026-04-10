from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class StrictModeViolation(RuntimeError):
    pass


@dataclass(slots=True)
class StrictModeSettings:
    fail_on_unmapped_high_risk: bool = True
    fail_on_pk_change: bool = True
    fail_on_fk_break: bool = True
    fail_on_invalid_pan: bool = True
    fail_on_invalid_iban: bool = True


def check_unmapped_high_risk(findings: list[dict[str, Any]], settings: StrictModeSettings | None = None) -> None:
    settings = settings or StrictModeSettings()
    if not settings.fail_on_unmapped_high_risk:
        return
    bad = [f for f in findings if f.get('risk') == 'high' and not f.get('service')]
    if bad:
        cols = ', '.join(f"{x.get('table')}.{x.get('column')}" for x in bad[:10])
        raise StrictModeViolation(f'Unmapped high-risk fields detected: {cols}')


def check_production_validation(report: dict[str, Any], settings: StrictModeSettings | None = None) -> None:
    settings = settings or StrictModeSettings()
    validation = report.get("validation", {}) if isinstance(report, dict) else {}
    problems: list[str] = []

    row_count = validation.get("row_count_check", {})
    if row_count.get("mismatched_tables"):
        problems.append("row count mismatch: " + ", ".join(row_count.get("mismatched_tables", [])[:10]))

    pk = validation.get("pk_stability", {})
    if settings.fail_on_pk_change and pk.get("mismatched_tables"):
        problems.append("pk stability mismatch: " + ", ".join(pk.get("mismatched_tables", [])[:10]))

    fk = validation.get("fk_integrity_check", {})
    if settings.fail_on_fk_break and fk.get("issues"):
        items = [f"{x.get('table')}.{x.get('column')}" for x in fk.get("issues", [])[:10]]
        problems.append("fk integrity issues: " + ", ".join(items))

    pan = validation.get("pan_validation", {})
    if settings.fail_on_invalid_pan and pan.get("masked_invalid", 0) > 0:
        problems.append(f"invalid PAN results: {pan.get('masked_invalid', 0)}")

    iban = validation.get("iban_validation", {})
    if settings.fail_on_invalid_iban and iban.get("masked_invalid", 0) > 0:
        problems.append(f"invalid IBAN-like results: {iban.get('masked_invalid', 0)}")

    if problems:
        raise StrictModeViolation("Production validation failed: " + " | ".join(problems))
