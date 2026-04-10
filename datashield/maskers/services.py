"""
Все 19 сервисов маскирования DataShield.
Полная реализация бизнес-логики из спецификации.
"""
from __future__ import annotations
import random
import re
import hashlib
from datetime import date, datetime, timedelta
from typing import Any

from .base import BaseMasker
from ..dictionaries import (
    FIRST_NAMES, LAST_NAMES, PATRONYMICS,
    PUBLIC_DOMAINS, CORPORATE_DOMAINS, TEMP_DOMAINS,
    VEHICLE_BRANDS, LEGAL_ENTITIES, FMS_UNITS, GIBDD_REGIONS,
    SYNTHETIC_ADDRESSES, REGIONS,
    get_names_by_gender_and_popularity, get_last_name_info, get_paired_last_name,
)


# ─── 1. BASIC (Посимвольное) ──────────────────────────────────────────────────
class BasicMasker(BaseMasker):
    service_name = "basic"

    def mask(self, value: Any, **kwargs) -> str:
        if value is None:
            return None
        s = str(value)
        return self.mask_with_cache(s, self.basic_mask_string, s)


# ─── 2. ФИО ───────────────────────────────────────────────────────────────────
class FioMasker(BaseMasker):
    service_name = "fio"

    def _detect_gender(self, last: str | None, first: str | None, patronymic: str | None) -> str:
        """Определить пол по ФИО."""
        for name, gender, _ in FIRST_NAMES:
            if name == first:
                return gender
        for name, gender, _ in PATRONYMICS:
            if name == patronymic:
                return gender
        if last:
            info = get_last_name_info(last)
            if info:
                for m, f, _, _ in LAST_NAMES:
                    if last == m:
                        return "M"
                    if last == f:
                        return "F"
        return "M"  # fallback

    def _get_first_info(self, name: str) -> tuple[str, int] | None:
        for n, g, p in FIRST_NAMES:
            if n == name:
                return g, p
        return None

    def _get_patronymic_info(self, name: str) -> tuple[str, int] | None:
        for n, g, p in PATRONYMICS:
            if n == name:
                return g, p
        return None

    def mask(self, value: Any = None, last: str | None = None,
             first: str | None = None, patronymic: str | None = None,
             household_key: str | None = None, **kwargs) -> dict:
        """
        Маскировать ФИО. Принимает как строку целиком, так и по компонентам.
        household_key: ключ домохозяйства для согласованной замены фамилии.
        """
        # Разбор строки если компоненты не переданы
        if value and not any([last, first, patronymic]):
            parts = str(value).strip().split()
            if len(parts) >= 1:
                last = parts[0]
            if len(parts) >= 2:
                first = parts[1]
            if len(parts) >= 3:
                patronymic = parts[2]

        cache_key = f"{last}|{first}|{patronymic}|{household_key}"

        def _do_mask():
            rnd = self._rnd(cache_key)
            gender = self._detect_gender(last, first, patronymic)

            # Маскировать фамилию
            new_last = last
            if last:
                info = get_last_name_info(last)
                if info:
                    # Найти новую фамилию той же популярности
                    same_pop = [
                        (m, f, p) for m, f, p, paired in LAST_NAMES
                        if abs(p - info["popularity"]) <= 1 and m != last and f != last
                    ]
                    if same_pop:
                        chosen = rnd.choice(same_pop)
                        new_last = chosen[0] if gender == "M" else chosen[1]
                    else:
                        new_last = self.basic_mask_string(last, rnd)
                else:
                    new_last = self.basic_mask_string(last, rnd)

            # Маскировать имя
            new_first = first
            if first:
                fi = self._get_first_info(first)
                if fi:
                    g, pop = fi
                    new_first = get_names_by_gender_and_popularity("first", g, pop, exclude=first)
                    new_first = rnd.choice([n for n, ng, _ in FIRST_NAMES if ng == g and n != first] or [first])
                else:
                    new_first = self.basic_mask_string(first, rnd)

            # Маскировать отчество
            new_patronymic = patronymic
            if patronymic:
                pi = self._get_patronymic_info(patronymic)
                if pi:
                    g, pop = pi
                    candidates = [n for n, ng, _ in PATRONYMICS if ng == g and n != patronymic]
                    new_patronymic = rnd.choice(candidates) if candidates else patronymic
                else:
                    new_patronymic = self.basic_mask_string(patronymic, rnd)

            result = {"last": new_last, "first": new_first, "patronymic": new_patronymic}
            if all([new_last, new_first, new_patronymic]):
                result["full"] = f"{new_last} {new_first} {new_patronymic}"
            elif all([new_last, new_first]):
                result["full"] = f"{new_last} {new_first}"
            else:
                result["full"] = new_last or ""
            return result

        return self.mask_with_cache(cache_key, _do_mask)


# ─── 3. ДАТА РОЖДЕНИЯ ─────────────────────────────────────────────────────────
class BirthdateMasker(BaseMasker):
    service_name = "birthdate"

    def _age_group(self, d: date) -> str:
        today = date.today()
        age = (today - d).days / 365.25
        if age < 14:
            return "under14"
        if age < 18:
            return "14to18"
        return "over18"

    def _safe_replace_year(self, d: date, new_year: int) -> date:
        try:
            return d.replace(year=new_year)
        except ValueError:
            # 29 Feb -> clamp to 28 Feb for non-leap years
            if d.month == 2 and d.day == 29:
                return date(new_year, 2, 28)
            raise

    def _shift_year_preserve_group(self, d: date, rnd: random.Random) -> date:
        group = self._age_group(d)
        for shift in rnd.sample([-2, -1, 1, 2], 4):
            new_year = d.year + shift
            new_date = self._safe_replace_year(d, new_year)
            if self._age_group(new_date) == group and new_date != d:
                return new_date
        # Fallback: preserve month/day as much as possible, but always change the value
        fallback_year = d.year + (1 if d.year < date.today().year else -1)
        new_date = self._safe_replace_year(d, fallback_year)
        if new_date == d:
            return date(d.year, d.month, 28) if d.month == 2 and d.day == 29 else d
        return new_date

    def mask(self, value: Any, **kwargs) -> date | None:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                d = date.fromisoformat(value)
            except ValueError:
                return value
        elif isinstance(value, date):
            d = value
        else:
            return value

        today = date.today()
        if d == today:
            return d

        rnd = self._rnd(str(d))

        # Замена дня и месяца
        new_month = rnd.randint(1, 12)
        max_day = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][new_month - 1]
        new_day = rnd.randint(1, max_day)

        # Обработка года
        if d.year < 1900:
            shift = rnd.choice([-2, -1, 1, 2])
            new_year = d.year + shift
            while new_year >= 1900:
                shift = rnd.choice([-2, -1, 1, 2])
                new_year = d.year + shift
        elif d > today:
            shift = rnd.choice([-2, -1, 1, 2])
            new_year = d.year + shift
        else:
            shifted = self._shift_year_preserve_group(d, rnd)
            new_year = shifted.year

        try:
            return date(new_year, new_month, new_day)
        except ValueError:
            return date(new_year, new_month, min(new_day, 28))


# ─── 4. ИНН ФЛ ────────────────────────────────────────────────────────────────
class InnMasker(BaseMasker):
    service_name = "inn"

    _WEIGHTS_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    _WEIGHTS_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

    def _checksum(self, digits: list[int], weights: list[int]) -> int:
        return sum(d * w for d, w in zip(digits, weights)) % 11 % 10

    def _is_valid_inn_fl(self, inn: str) -> bool:
        if not re.match(r"^\d{12}$", inn):
            return False
        d = [int(c) for c in inn]
        c11 = self._checksum(d[:10], self._WEIGHTS_11)
        c12 = self._checksum(d[:11], self._WEIGHTS_12)
        return d[10] == c11 and d[11] == c12

    def _is_valid_inn_ul(self, inn: str) -> bool:
        if not re.match(r"^\d{10}$", inn):
            return False
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        d = [int(c) for c in inn]
        ctrl = sum(d[i] * weights[i] for i in range(9)) % 11 % 10
        return d[9] == ctrl

    def _generate_inn_fl(self, rnd: random.Random, region_prefix: str | None = None) -> str:
        prefix = region_prefix if region_prefix and len(region_prefix) == 4 else f"{rnd.randint(10, 99)}{rnd.randint(10, 99)}"
        body = "".join(str(rnd.randint(0, 9)) for _ in range(6))
        base10 = prefix + body
        d = [int(c) for c in base10]
        c11 = self._checksum(d[:10], self._WEIGHTS_11)
        c12 = self._checksum(d[:10] + [c11], self._WEIGHTS_12)
        return base10 + str(c11) + str(c12)

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        rnd = self._rnd(s)

        if re.match(r"^\d{12}$", s):
            region_prefix = s[:4]
            return self.mask_with_cache(s, self._generate_inn_fl, rnd, region_prefix)
        elif re.match(r"^\d{10}$", s):
            return self.mask_with_cache(s, self._mask_inn_ul, s, rnd)
        else:
            return self.mask_with_cache(s, self.basic_mask_string, s)

    def _mask_inn_ul(self, original: str, rnd: random.Random) -> str:
        prefix = original[:2]
        body = "".join(str(rnd.randint(0, 9)) for _ in range(7))
        base = prefix + body
        d = [int(c) for c in base]
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        ctrl = sum(d[i] * weights[i] for i in range(9)) % 11 % 10
        return base + str(ctrl)


# ─── 5. СНИЛС ─────────────────────────────────────────────────────────────────
class SnilsMasker(BaseMasker):
    service_name = "snils"

    def _is_valid(self, s: str) -> bool:
        digits = re.sub(r"\D", "", s)
        if len(digits) != 11:
            return False
        n = [int(c) for c in digits[:9]]
        check = sum(n[i] * (9 - i) for i in range(9)) % 101
        if check in (100, 101):
            check = 0
        return int(digits[9:11]) == check

    def _generate(self, rnd: random.Random) -> str:
        while True:
            digits = [rnd.randint(0, 9) for _ in range(9)]
            check = sum(digits[i] * (9 - i) for i in range(9)) % 101
            if check >= 100:
                check = 0
            base = "".join(str(d) for d in digits) + f"{check:02d}"
            return f"{base[:3]}-{base[3:6]}-{base[6:9]} {base[9:11]}"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        rnd = self._rnd(s)
        if self._is_valid(s):
            return self.mask_with_cache(s, self._generate, rnd)
        return self.mask_with_cache(s, self.basic_mask_string, s)


# ─── 6. МЕСТО РОЖДЕНИЯ ────────────────────────────────────────────────────────
class BirthplaceMasker(BaseMasker):
    service_name = "birthplace"

    _REGIONS_PATTERN = re.compile(
        r"\b(Москва|Санкт-Петербург|Московская|Ленинградская|Краснодарский|"
        r"область|край|республика|г\.|город)\b", re.IGNORECASE
    )

    def _detect_region(self, s: str) -> str | None:
        for code, info in REGIONS.items():
            if info["name"].lower() in s.lower():
                return code
        return None

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        rnd = self._rnd(s)
        region_code = self._detect_region(s)
        if region_code:
            region_name = REGIONS[region_code]["name"]
            addrs = SYNTHETIC_ADDRESSES.get(region_code, SYNTHETIC_ADDRESSES["default"])
            chosen = rnd.choice(addrs)
            return f"{region_name}, {chosen['city']}, {chosen['street']}, д. {chosen['house']}"
        return self.basic_mask_string(s, rnd)


# ─── 7. БАНКОВСКАЯ КАРТА ──────────────────────────────────────────────────────
class BankCardMasker(BaseMasker):
    service_name = "bankCard"

    def _luhn_checksum(self, number: str) -> int:
        digits = [int(d) for d in number]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        total = sum(odd_digits)
        for d in even_digits:
            total += sum(divmod(d * 2, 10))
        return total % 10

    def _is_valid_card(self, number: str) -> bool:
        clean = re.sub(r"\D", "", number)
        if not (13 <= len(clean) <= 16):
            return False
        return self._luhn_checksum(clean) == 0

    def _generate_card(self, bin6: str, length: int, valid: bool, rnd: random.Random) -> str:
        # Генерировать цифры 7..len-1, установить контрольную цифру
        middle = "".join(str(rnd.randint(0, 9)) for _ in range(length - 7))
        if valid:
            partial = bin6 + middle + "0"
            for check in range(10):
                candidate = bin6 + middle + str(check)
                if self._luhn_checksum(candidate) == 0:
                    return candidate
            return bin6 + middle + "0"
        else:
            candidate = bin6 + middle + str(rnd.randint(0, 9))
            while self._luhn_checksum(candidate) == 0:
                candidate = bin6 + middle + str(rnd.randint(0, 9))
            return candidate

    def mask_number(self, number: str | None, rnd: random.Random) -> str | None:
        if not number:
            return number
        clean = re.sub(r"\D", "", number)
        if not (13 <= len(clean) <= 16):
            return self.basic_mask_string(number, rnd)
        bin6 = clean[:6]
        valid = self._is_valid_card(clean)
        return self._generate_card(bin6, len(clean), valid, rnd)

    def mask_expiry(self, expiry: str | None, rnd: random.Random) -> str | None:
        if not expiry:
            return expiry
        m = re.match(r"(\d{1,2})[/\-](\d{2,4})", expiry)
        if not m:
            return self.basic_mask_string(expiry, rnd)
        month_s, year_s = m.group(1), m.group(2)
        month = int(month_s)
        year = int(year_s) if len(year_s) == 4 else 2000 + int(year_s)
        today = date.today()
        # Маскировка года
        if year < today.year:
            new_year = year + rnd.choice([-1, 1])
            while new_year >= today.year:
                new_year = year + rnd.choice([-2, -1])
        elif year == today.year:
            new_year = year
        else:
            new_year = year + rnd.choice([-1, 0, 1])
            new_year = max(today.year, new_year)
        # Маскировка месяца
        if month == today.month:
            new_month = month
        else:
            new_month = rnd.randint(1, 12)
            while new_month == month:
                new_month = rnd.randint(1, 12)
        yr_str = str(new_year)[-2:] if len(year_s) == 2 else str(new_year)
        return f"{new_month:02d}/{yr_str}"

    def mask_holder(self, holder: str | None, rnd: random.Random) -> str | None:
        if not holder:
            return holder
        parts = holder.strip().split()
        if len(parts) < 2:
            return self.basic_mask_string(holder, rnd)
        # Попытка найти в словаре (транслит)
        new_last = self.basic_mask_string(parts[0], rnd)
        new_first = self.basic_mask_string(parts[1], rnd)
        return f"{new_last} {new_first}"

    def mask(self, value: Any = None, number: str | None = None,
             expiry: str | None = None, holder: str | None = None,
             cvv: str | None = None, **kwargs) -> dict:
        if value and not number:
            number = str(value)
        cache_key = f"{number}|{expiry}|{holder}"
        rnd = self._rnd(cache_key)

        masked_number = self.mask_with_cache(f"num:{number}", self.mask_number, number, rnd)
        masked_expiry = self.mask_with_cache(f"exp:{expiry}", self.mask_expiry, expiry, rnd)
        masked_holder = self.mask_with_cache(f"hld:{holder}", self.mask_holder, holder, rnd)
        return {
            "number": masked_number,
            "pan": masked_number,
            "expiry": masked_expiry,
            "holder": masked_holder,
            "holder_name": masked_holder,
            "cvv": self.basic_mask_string(cvv, rnd) if cvv else None,
        }


# ─── 8. ПАСПОРТ ───────────────────────────────────────────────────────────────
class PassportMasker(BaseMasker):
    service_name = "passport"

    def _get_region_from_series(self, series: str) -> str | None:
        digits = re.sub(r"\D", "", series)
        return digits[:2] if len(digits) >= 2 else None

    def _mask_issue_date(self, issue_date: date, birth_date: date | None, rnd: random.Random) -> date:
        if birth_date:
            age_at_issue = (issue_date - birth_date).days // 365
            new_birth = BirthdateMasker().mask(birth_date)
            try:
                return new_birth.replace(year=new_birth.year + age_at_issue)
            except Exception:
                pass
        shift = rnd.choice([-2, -1, 1, 2])
        try:
            return issue_date.replace(year=issue_date.year + shift)
        except ValueError:
            return issue_date

    def mask(self, value: Any = None, series: str | None = None,
             number: str | None = None, issue_date: date | None = None,
             expiry_date: date | None = None, birth_date: date | None = None,
             issuer: str | None = None, issuer_code: str | None = None, **kwargs) -> dict | str:

        if value is not None and not any([series, number, issue_date, expiry_date, birth_date, issuer, issuer_code]):
            raw = str(value).strip()
            if not raw:
                return raw
            return self.mask_with_cache(f"scalar:{raw}", self.basic_mask_string, raw, self._rnd(raw))

        cache_key = f"{series}|{number}|{issue_date}|{birth_date}"
        rnd = self._rnd(cache_key)

        # Серия: сохранить первые 2 цифры (регион)
        new_series = series
        if series:
            region = self._get_region_from_series(series)
            if region:
                rest = self.basic_mask_string(series[2:], rnd)
                new_series = region + rest
            else:
                new_series = self.basic_mask_string(series, rnd)

        # Номер: посимвольно
        new_number = self.basic_mask_string(number, rnd) if number else None

        # Код подразделения и подразделение
        region_code = self._get_region_from_series(series) if series else None
        new_issuer_code, new_issuer = issuer_code, issuer
        if issuer_code:
            units = FMS_UNITS.get(region_code or "default", FMS_UNITS["default"])
            chosen = rnd.choice(units)
            new_issuer_code = chosen["code"]
            new_issuer = chosen["name"]

        # Дата выдачи
        new_issue_date = issue_date
        if issue_date:
            new_issue_date = self._mask_issue_date(issue_date, birth_date, rnd)

        # Дата истечения
        new_expiry = expiry_date
        if expiry_date and issue_date:
            validity = (expiry_date - issue_date).days
            if new_issue_date:
                try:
                    new_expiry = new_issue_date + timedelta(days=validity)
                except Exception:
                    pass

        return {
            "series": new_series,
            "number": new_number,
            "issue_date": new_issue_date,
            "expiry_date": new_expiry,
            "issuer_code": new_issuer_code,
            "issuer": new_issuer,
        }


# ─── 9. ВОДИТЕЛЬСКОЕ УДОСТОВЕРЕНИЕ ───────────────────────────────────────────
class DrivingLicenseMasker(BaseMasker):
    service_name = "drivingLicense"

    def mask(self, value: Any = None, series: str | None = None,
             number: str | None = None, issue_date: date | None = None,
             expiry_date: date | None = None, birth_date: date | None = None,
             gibdd_code: str | None = None, **kwargs) -> dict:

        cache_key = f"{series}|{number}|{issue_date}|{birth_date}"
        rnd = self._rnd(cache_key)
        sign = rnd.choice([-1, 1])

        # Серия: сохранить первые 2 цифры
        new_series = series
        if series:
            m = re.match(r"^(\d{2})(.*)", series)
            if m:
                new_series = m.group(1) + self.basic_mask_string(m.group(2), rnd)
            else:
                new_series = self.basic_mask_string(series, rnd)

        # Номер: случайные 6 цифр
        new_number = "".join(str(rnd.randint(0, 9)) for _ in range(6))

        # Код ГИБДД
        new_gibdd = gibdd_code
        if gibdd_code:
            region_m = re.match(r"(?:ГИБДД\s*)?(\d{2})", gibdd_code)
            if region_m:
                reg = region_m.group(1)
                units = GIBDD_REGIONS.get(reg, GIBDD_REGIONS["default"])
                new_gibdd = rnd.choice(units)
            else:
                new_gibdd = self.basic_mask_string(gibdd_code, rnd)

        # Дата рождения
        new_birth = birth_date
        if birth_date:
            new_birth = BirthdateMasker().mask(birth_date)

        # Дата выдачи
        new_issue = issue_date
        if issue_date:
            try:
                new_issue = issue_date.replace(year=issue_date.year + sign)
            except ValueError:
                new_issue = issue_date

        # Дата истечения
        new_expiry = expiry_date
        if expiry_date:
            if issue_date:
                validity = (expiry_date - issue_date).days
                if new_issue:
                    new_expiry = new_issue + timedelta(days=validity)
            elif birth_date:
                delta = (expiry_date - birth_date).days
                if new_birth:
                    new_expiry = new_birth + timedelta(days=delta)
            else:
                try:
                    new_expiry = expiry_date.replace(year=expiry_date.year + sign)
                except ValueError:
                    pass

        return {
            "series": new_series,
            "number": new_number,
            "issue_date": new_issue,
            "expiry_date": new_expiry,
            "birth_date": new_birth,
            "gibdd_code": new_gibdd,
        }


# ─── 10. ДАННЫЕ ЮЛ/ИП ────────────────────────────────────────────────────────
class LegalDetailsMasker(BaseMasker):
    service_name = "legalDetails"

    def _detect_type(self, inn: str | None, ogrn: str | None, name: str | None) -> str:
        if inn:
            clean = re.sub(r"\D", "", inn)
            if len(clean) == 10:
                return "ЮЛ"
            if len(clean) == 12:
                return "ИП"
        if ogrn:
            clean = re.sub(r"\D", "", ogrn)
            if len(clean) == 13:
                return "ЮЛ"
            if len(clean) == 15:
                return "ИП"
        if name:
            ip_keywords = ["ПБОЮЛ", "ИЧП", " ЧП ", " ИП ", "(ИП)", "НОТАРИУС", "ГКФХ", "АДВОКАТ"]
            for kw in ip_keywords:
                if kw.upper() in name.upper():
                    return "ИП"
            return "ЮЛ"
        return "ЮЛ"

    def mask(self, value: Any = None, full_name: str | None = None,
             short_name: str | None = None, inn: str | None = None,
             ogrn: str | None = None, kpp: str | None = None, **kwargs) -> dict:

        cache_key = f"{inn}|{ogrn}|{full_name}"
        rnd = self._rnd(cache_key)
        entity_type = self._detect_type(inn, ogrn, full_name or short_name)

        pool = [e for e in LEGAL_ENTITIES if e["type"] == entity_type]
        if not pool:
            pool = LEGAL_ENTITIES
        chosen = rnd.choice(pool)

        return {
            "full_name": chosen["full_name"],
            "short_name": chosen["short_name"],
            "inn": chosen["inn"],
            "ogrn": chosen["ogrn"],
            "kpp": chosen["kpp"],
        }


# ─── 11. АДРЕС ────────────────────────────────────────────────────────────────
class AddressMasker(BaseMasker):
    service_name = "cdiAddress"

    def _detect_region(self, s: str) -> str | None:
        for code, info in REGIONS.items():
            if info["name"].lower() in s.lower():
                return code
        return None

    def mask(self, value: Any = None, region: str | None = None,
             city: str | None = None, street: str | None = None,
             house: str | None = None, apartment: str | None = None,
             **kwargs) -> dict:

        s = str(value) if value else f"{city or ''} {street or ''} {house or ''}".strip()
        rnd = self._rnd(s)

        region_code = region or self._detect_region(s)
        addrs = SYNTHETIC_ADDRESSES.get(region_code or "default", SYNTHETIC_ADDRESSES["default"])
        chosen = rnd.choice(addrs)
        region_name = REGIONS.get(region_code, {}).get("name", region or "")

        new_apt = self.basic_mask_string(apartment, rnd) if apartment else None

        return {
            "region": region_name,
            "city": chosen["city"],
            "street": chosen["street"],
            "house": chosen["house"],
            "apartment": new_apt,
            "full": f"{region_name}, г. {chosen['city']}, {chosen['street']}, д. {chosen['house']}" +
                    (f", кв. {new_apt}" if new_apt else ""),
        }


# ─── 12. РАСЧЁТНЫЙ СЧЁТ ──────────────────────────────────────────────────────
class BankAccountMasker(BaseMasker):
    service_name = "bankAccount"

    def _check_digit(self, account: str, bik: str) -> int:
        """Расчёт контрольного разряда счёта с БИК."""
        key = bik[-3:] + account
        weights = [7, 1, 3] * 7 + [7, 1]
        return sum(int(key[i]) * weights[i] % 10 for i in range(len(weights))) % 10

    def _is_valid_account(self, account: str, bik: str | None) -> bool:
        if not re.match(r"^\d{20}$", account):
            return False
        if bik and re.match(r"^\d{9}$", bik):
            return self._check_digit(account, bik) == 0
        return True  # Нет БИК — считаем условно валидным

    def mask(self, value: Any = None, bik: str | None = None, **kwargs) -> str | None:
        if value is None:
            return None
        account = str(value).strip()
        rnd = self._rnd(f"{account}|{bik}")

        if not re.match(r"^\d{20}$", account):
            return self.basic_mask_string(account, rnd)

        valid = self._is_valid_account(account, bik)

        # Сохраняем: 1-8 (балансовые счета + валюта), 10-13 (код подразделения)
        prefix = account[:8]
        division = account[9:13]
        # Генерируем 14-20 (7 цифр)
        tail = "".join(str(rnd.randint(0, 9)) for _ in range(7))
        partial = prefix + "0" + division + tail  # digit 9 = placeholder

        if valid and bik and re.match(r"^\d{9}$", bik):
            # Подобрать контрольный разряд
            for d in range(10):
                candidate = prefix + str(d) + division + tail
                if self._check_digit(candidate, bik) == 0:
                    if valid:
                        return candidate
                    break
            return prefix + str(rnd.randint(0, 9)) + division + tail
        else:
            return prefix + str(rnd.randint(0, 9)) + division + tail


# ─── 13. ТЕЛЕФОН ──────────────────────────────────────────────────────────────
class PhoneMasker(BaseMasker):
    service_name = "phone"

    _BY_PATTERN = re.compile(r"^(\+375)[\s\-]?\(?(\d{2})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})$")
    _RU_PATTERN = re.compile(r"^(\+7|8|7)[\s\-]?\(?(\d{3})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})$")

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        rnd = self._rnd(s)
        m = self._BY_PATTERN.match(s)
        if m:
            operator = m.group(2)
            new_tail = "".join(str(rnd.randint(0, 9)) for _ in range(7))
            return f"+375 ({operator}) {new_tail[:3]}-{new_tail[3:5]}-{new_tail[5:7]}"
        m = self._RU_PATTERN.match(s)
        if m:
            operator = m.group(2)
            new_tail = "".join(str(rnd.randint(0, 9)) for _ in range(7))
            return f"+7 ({operator}) {new_tail[:3]}-{new_tail[3:5]}-{new_tail[5:7]}"
        return self.basic_mask_string(s, rnd)


class SimplePhoneMasker(BaseMasker):
    service_name = "simple_phone"

    MASKS = [
        (re.compile(r"^\+375\d{9}$"), "+375XXXXXXXXX"),
        (re.compile(r"^\+7\d{10}$"), "+7XXXXXXXXXX"),
        (re.compile(r"^8\d{10}$"), "8XXXXXXXXXX"),
        (re.compile(r"^\d{10,11}$"), "XXXXXXXXXXX"),
    ]

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        rnd = self._rnd(s)
        for pattern, _ in self.MASKS:
            if pattern.match(s):
                prefix = s[:4] if s.startswith("+375") else (s[:2] if s.startswith("+7") else (s[:1] if s.startswith("8") else ""))
                rest = s[len(prefix):]
                return prefix + "".join(str(rnd.randint(0, 9)) for _ in rest)
        return self.basic_mask_string(s, rnd)


# ─── 14. EMAIL ────────────────────────────────────────────────────────────────
class EmailMasker(BaseMasker):
    service_name = "email"

    def _classify_domain(self, domain: str) -> str:
        d = domain.lower()
        if d in PUBLIC_DOMAINS:
            return "public"
        if d in TEMP_DOMAINS:
            return "temp"
        return "corporate"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        rnd = self._rnd(s)
        if "@" not in s:
            return self.basic_mask_string(s, rnd)
        parts = s.rsplit("@", 1)
        account, domain = parts[0], parts[1]
        new_account = self.basic_mask_string(account, rnd)
        domain_type = self._classify_domain(domain)
        if domain_type == "public":
            new_domain = rnd.choice(PUBLIC_DOMAINS)
        elif domain_type == "temp":
            new_domain = rnd.choice(TEMP_DOMAINS)
        else:
            new_domain = rnd.choice(CORPORATE_DOMAINS)
        return f"{new_account}@{new_domain}"


# ─── 15. ПТС (Паспорт ТС) ────────────────────────────────────────────────────
class VehiclePassportMasker(BaseMasker):
    service_name = "vehiclePassport"

    def _is_valid_vin(self, vin: str) -> bool:
        if len(vin) != 17:
            return False
        invalid = set("IOQ")
        return all(c.upper() not in invalid for c in vin)

    def _mask_vin(self, vin: str, rnd: random.Random) -> str:
        valid_chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
        return "".join(rnd.choice(valid_chars) for _ in vin)

    def mask(self, value: Any = None, series: str | None = None,
             number: str | None = None, issue_date: date | None = None,
             vin: str | None = None, brand: str | None = None,
             model: str | None = None, year: int | None = None,
             engine_num: str | None = None, chassis_num: str | None = None,
             body_num: str | None = None, **kwargs) -> dict:

        cache_key = f"{series}|{vin}|{brand}"
        rnd = self._rnd(cache_key)

        # Серия: XXAA формат → сохранить регион (XX), заменить буквы
        new_series = series
        if series:
            m = re.match(r"^(\d{2})([А-ЯA-Z]{2})$", series)
            if m:
                cyrillic_letters = "АВЕКМНОРСТУХ"
                new_series = m.group(1) + "".join(rnd.choice(cyrillic_letters) for _ in m.group(2))
            else:
                new_series = self.basic_mask_string(series, rnd)

        new_number = self.basic_mask_string(number, rnd) if number else None

        # Дата выдачи
        new_issue = issue_date
        if issue_date:
            new_issue = BirthdateMasker().mask(issue_date)

        # VIN
        new_vin = vin
        if vin:
            if self._is_valid_vin(vin):
                new_vin = self._mask_vin(vin, rnd)
            else:
                new_vin = self.basic_mask_string(vin, rnd)

        # Марка и модель
        new_brand = brand
        new_model = model
        brands_list = list(VEHICLE_BRANDS.keys())
        if brand and brand in VEHICLE_BRANDS:
            new_brand = rnd.choice([b for b in brands_list if b != brand] or brands_list)
        elif brand:
            new_brand = rnd.choice(brands_list)
        if new_brand and new_brand in VEHICLE_BRANDS:
            models = VEHICLE_BRANDS[new_brand]
            new_model = rnd.choice(models)

        # Год изготовления: сохранить дельту с датой выдачи
        new_year = year
        if year and issue_date and new_issue:
            delta = issue_date.year - year
            new_year = new_issue.year - delta

        return {
            "series": new_series,
            "number": new_number,
            "issue_date": new_issue,
            "vin": new_vin,
            "brand": new_brand,
            "model": new_model,
            "year": new_year,
            "engine_num": self.basic_mask_string(engine_num, rnd) if engine_num else None,
            "chassis_num": self.basic_mask_string(chassis_num, rnd) if chassis_num else None,
            "body_num": self.basic_mask_string(body_num, rnd) if body_num else None,
        }


# ─── 16. ЧИСЛО ────────────────────────────────────────────────────────────────
class IdentifierMasker(BaseMasker):
    service_name = "identifier"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        return self.mask_with_cache(f"id:{raw}", self.basic_mask_string, raw, self._rnd(raw))


class TaxIdMasker(BaseMasker):
    service_name = "taxId"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        rnd = self._rnd(raw)
        digits = re.sub(r"\D", "", raw)
        if digits:
            masked_digits = "".join(str((int(ch) + rnd.randint(1, 9)) % 10) for ch in digits)
            out = []
            idx = 0
            for ch in raw:
                if ch.isdigit():
                    out.append(masked_digits[idx])
                    idx += 1
                else:
                    out.append(ch)
            return "".join(out)
        return self.basic_mask_string(raw, rnd)


class CityMasker(BaseMasker):
    service_name = "city"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        rnd = self._rnd(raw)
        cities = ["Минск", "Гомель", "Брест", "Гродно", "Витебск", "Могилёв"]
        normalized = raw.lower().replace("г. ", "").strip()
        candidates = [c for c in cities if c.lower() != normalized]
        chosen = rnd.choice(candidates or cities)
        return f"г. {chosen}" if raw.lower().startswith("г.") else chosen


class IpAddressMasker(BaseMasker):
    service_name = "ipAddress"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        rnd = self._rnd(raw)
        m = re.fullmatch(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})", raw)
        if not m:
            return self.basic_mask_string(raw, rnd)
        octets = [int(x) for x in m.groups()]
        if octets[0] == 10:
            new = [10, rnd.randint(0,255), rnd.randint(0,255), rnd.randint(1,254)]
        elif octets[0] == 172 and 16 <= octets[1] <= 31:
            new = [172, rnd.randint(16,31), rnd.randint(0,255), rnd.randint(1,254)]
        elif octets[0] == 192 and octets[1] == 168:
            new = [192, 168, rnd.randint(0,255), rnd.randint(1,254)]
        else:
            new = [rnd.choice([11,23,31,45,62,77,89,95,101,145,176,185,203]), rnd.randint(0,255), rnd.randint(0,255), rnd.randint(1,254)]
        return ".".join(str(x) for x in new)


class DeviceIdMasker(BaseMasker):
    service_name = "deviceId"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        return self.mask_with_cache(f"device:{raw}", self.basic_mask_string, raw, self._rnd(raw))


class TextMasker(BaseMasker):
    service_name = "text"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value)
        if not raw:
            return raw
        rnd = self._rnd(raw)
        words = raw.split()
        if len(words) > 1:
            return " ".join(self.basic_mask_string(w, rnd) for w in words)
        return self.basic_mask_string(raw, rnd)


class CardExpiryMasker(BaseMasker):
    service_name = "cardExpiry"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        return BankCardMasker(cache=self._cache, mode=self._mode).mask_expiry(str(value), self._rnd(str(value)))


class CardHolderMasker(BaseMasker):
    service_name = "cardHolder"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        return BankCardMasker(cache=self._cache, mode=self._mode).mask_holder(str(value), self._rnd(str(value)))


class DynamicContactMasker(BaseMasker):
    service_name = "dynamicContact"

    def mask(self, value: Any, contact_type: str | None = None, kind: str | None = None, row: dict | None = None, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        type_hint = (contact_type or kind or "").strip().lower()
        if not type_hint and row:
            type_hint = str(row.get("contact_type") or row.get("type") or "").strip().lower()
        if not type_hint:
            if "@" in raw:
                type_hint = "email"
            elif re.search(r"\+?\d", raw):
                type_hint = "phone"
        if type_hint in {"email", "e-mail", "mail", "почта"}:
            return EmailMasker(cache=self._cache, mode=self._mode).mask(raw)
        if type_hint in {"phone", "mobile", "телефон", "tel", "msisdn"}:
            return PhoneMasker(cache=self._cache, mode=self._mode).mask(raw)
        return self.basic_mask_string(raw, self._rnd(raw))


class RegionMasker(BaseMasker):
    service_name = "region"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        rnd = self._rnd(raw)
        values = [info["name"] for code, info in REGIONS.items() if code != "default"]
        norm = raw.lower()
        candidates = [v for v in values if v.lower() != norm]
        if candidates:
            return rnd.choice(candidates)
        return self.basic_mask_string(raw, rnd)


class DateTimeMasker(BaseMasker):
    service_name = "datetime"

    def mask(self, value: Any, **kwargs) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return self.basic_mask_string(raw, self._rnd(raw))
        rnd = self._rnd(raw)
        shift_days = rnd.choice([-5, -3, -2, 2, 3, 5])
        shift_minutes = rnd.randint(7, 137)
        masked = dt + timedelta(days=shift_days, minutes=shift_minutes)
        return masked.isoformat(timespec="seconds")


class NumberMasker(BaseMasker):
    service_name = "number"

    def mask(self, value: Any,
             blur_type: str = "percent",  # percent | units
             blur_value: float = 20.0,
             preserve_sign: bool = True,
             preserve_zero: bool = True,
             **kwargs) -> Any:
        if value is None:
            return None
        try:
            num = float(str(value).replace(",", "."))
        except ValueError:
            return value

        if preserve_zero and num == 0:
            return value

        rnd = self._rnd(str(value))
        if blur_value == 0:
            return self.basic_mask_string(str(value), rnd)

        if blur_type == "percent":
            delta = abs(num) * blur_value / 100
        else:
            delta = blur_value

        masked = num + rnd.uniform(-delta, delta)
        if preserve_sign and num != 0:
            if num > 0 and masked <= 0:
                masked = abs(masked)
            elif num < 0 and masked >= 0:
                masked = -abs(masked)

        if isinstance(value, int) or (isinstance(value, str) and "." not in str(value)):
            return int(round(masked))
        return round(masked, 2)
