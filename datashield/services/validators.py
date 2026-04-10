from __future__ import annotations

from typing import Iterable


def validate_pan_luhn(number: str | None) -> bool:
    if not number:
        return False
    digits = ''.join(ch for ch in str(number) if ch.isdigit())
    if len(digits) < 12:
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def validate_iban_like(value: str | None) -> bool:
    if not value:
        return False
    raw = ''.join(ch for ch in str(value).upper() if ch.isalnum())
    return len(raw) >= 15 and raw[:2].isalpha() and raw[2:4].isdigit()


def summarize_validation(rows: Iterable[dict]) -> dict[str, int]:
    summary = {'total': 0, 'pan_valid': 0, 'iban_like': 0}
    for row in rows:
        summary['total'] += 1
        if validate_pan_luhn(row.get('pan')):
            summary['pan_valid'] += 1
        if validate_iban_like(row.get('iban')):
            summary['iban_like'] += 1
    return summary
