"""
Тесты сервисов маскирования DataShield.
Запуск: python -m pytest tests/ -v
"""
import sys
sys.path.insert(0, '..')

import pytest
from datetime import date
from datashield.maskers.services import (
    BasicMasker, FioMasker, BirthdateMasker, InnMasker, SnilsMasker,
    EmailMasker, PhoneMasker, BankCardMasker, BankAccountMasker,
    NumberMasker, LegalDetailsMasker, PassportMasker,
)


# ── BasicMasker ───────────────────────────────────────────────────────────────
class TestBasicMasker:
    def setup_method(self):
        self.m = BasicMasker()

    def test_length_preserved(self):
        s = "Иванов123"
        result = self.m.mask(s)
        assert len(result) == len(s)

    def test_digits_to_digits(self):
        result = self.m.mask("12345")
        assert result.isdigit()

    def test_cyrillic_vowels_preserved(self):
        vowels = "аеёиоуыьъэюя"
        for v in vowels:
            result = self.m.mask(v)
            assert result in vowels, f"Гласная {v} → {result} не является гласной"

    def test_special_chars_preserved(self):
        result = self.m.mask("test@mail.ru")
        assert "@" in result
        assert "." in result

    def test_none_returns_none(self):
        assert self.m.mask(None) is None

    def test_deterministic(self):
        assert self.m.mask("Иванов") == self.m.mask("Иванов")


# ── FioMasker ─────────────────────────────────────────────────────────────────
class TestFioMasker:
    def setup_method(self):
        self.m = FioMasker()

    def test_returns_dict(self):
        result = self.m.mask("Иванов Пётр Сергеевич")
        assert isinstance(result, dict)
        assert "last" in result
        assert "first" in result

    def test_deterministic(self):
        r1 = self.m.mask("Иванов Пётр Сергеевич")
        r2 = self.m.mask("Иванов Пётр Сергеевич")
        assert r1 == r2

    def test_different_inputs_different_outputs(self):
        r1 = self.m.mask("Иванов Пётр Сергеевич")
        r2 = self.m.mask("Смирнов Алексей Иванович")
        assert r1["last"] != r2["last"]

    def test_name_changed(self):
        result = self.m.mask("Иванов Пётр Сергеевич")
        assert result["last"] != "Иванов"


# ── BirthdateMasker ───────────────────────────────────────────────────────────
class TestBirthdateMasker:
    def setup_method(self):
        self.m = BirthdateMasker()

    def test_adult_stays_adult(self):
        d = date(1985, 3, 15)
        result = self.m.mask(d)
        today = date.today()
        age = (today - result).days / 365.25
        assert age >= 18, f"Взрослый стал {age:.1f} лет"

    def test_current_date_unchanged(self):
        today = date.today()
        assert self.m.mask(today) == today

    def test_pre_1900_stays_pre_1900(self):
        d = date(1890, 5, 10)
        result = self.m.mask(d)
        assert result.year < 1900

    def test_changed(self):
        d = date(1985, 3, 15)
        result = self.m.mask(d)
        assert result != d

    def test_returns_date(self):
        result = self.m.mask("1990-01-15")
        assert isinstance(result, date)

    def test_feb29_changes_safely(self):
        d = date(1988, 2, 29)
        result = self.m.mask(d)
        assert result != d
        assert isinstance(result, date)


# ── InnMasker ─────────────────────────────────────────────────────────────────
class TestInnMasker:
    def setup_method(self):
        self.m = InnMasker()

    def test_valid_inn_fl(self):
        result = self.m.mask("770912345601")
        assert len(result) == 12, f"Длина INN: {len(result)}"
        # Проверить контрольную сумму
        d = [int(c) for c in result]
        w11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        w12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c11 = sum(d[i] * w11[i] for i in range(10)) % 11 % 10
        c12 = sum(d[i] * w12[i] for i in range(11)) % 11 % 10
        assert d[10] == c11 and d[11] == c12, f"Контрольная сумма ИНН неверна: {result}"

    def test_deterministic(self):
        inn = "770912345601"
        assert self.m.mask(inn) == self.m.mask(inn)

    def test_invalid_inn_masked_charwise(self):
        result = self.m.mask("ABC123")
        assert result is not None
        assert len(result) == len("ABC123")


# ── SnilsMasker ───────────────────────────────────────────────────────────────
class TestSnilsMasker:
    def setup_method(self):
        self.m = SnilsMasker()

    def test_valid_snils_format(self):
        result = self.m.mask("112-233-445 95")
        assert "-" in result or len(result) > 9

    def test_deterministic(self):
        snils = "112-233-445 95"
        assert self.m.mask(snils) == self.m.mask(snils)


# ── EmailMasker ───────────────────────────────────────────────────────────────
class TestEmailMasker:
    def setup_method(self):
        self.m = EmailMasker()

    def test_structure_preserved(self):
        result = self.m.mask("petr.ivanov@gmail.com")
        assert "@" in result

    def test_public_domain_replaced_with_public(self):
        from datashield.dictionaries import PUBLIC_DOMAINS
        result = self.m.mask("user@gmail.com")
        domain = result.split("@")[1]
        assert domain in PUBLIC_DOMAINS

    def test_none_returns_none(self):
        assert self.m.mask(None) is None

    def test_deterministic(self):
        e = "ivanov@yandex.ru"
        assert self.m.mask(e) == self.m.mask(e)


# ── PhoneMasker ───────────────────────────────────────────────────────────────
class TestPhoneMasker:
    def setup_method(self):
        self.m = PhoneMasker()

    def test_country_code_preserved(self):
        result = self.m.mask("+7 (916) 123-45-67")
        assert result.startswith("+7")

    def test_operator_code_preserved(self):
        result = self.m.mask("+7 (916) 123-45-67")
        assert "916" in result

    def test_deterministic(self):
        p = "+7 (916) 123-45-67"
        assert self.m.mask(p) == self.m.mask(p)


# ── BankCardMasker ────────────────────────────────────────────────────────────
class TestBankCardMasker:
    def setup_method(self):
        self.m = BankCardMasker()

    def test_bin_preserved(self):
        result = self.m.mask(number="4111111111111111")
        assert result["number"][:6] == "411111"

    def test_luhn_valid_card_stays_valid(self):
        result = self.m.mask(number="4111111111111111")
        num = result["number"]
        assert self.m._is_valid_card(num), f"Карта должна быть валидна: {num}"

    def test_length_preserved(self):
        result = self.m.mask(number="4111111111111111")
        assert len(result["number"]) == 16

    def test_linked_fields_present(self):
        result = self.m.mask(number="4111111111111111", expiry="12/29", holder="ANDREY SOKOLOV")
        assert result["pan"] == result["number"]
        assert "holder_name" in result and result["holder_name"] != "ANDREY SOKOLOV"
        assert result["expiry"] != "12/29"


# ── NumberMasker ──────────────────────────────────────────────────────────────
class TestNumberMasker:
    def setup_method(self):
        self.m = NumberMasker()

    def test_positive_stays_positive(self):
        result = self.m.mask(1000, preserve_sign=True, blur_value=10)
        assert result > 0

    def test_negative_stays_negative(self):
        result = self.m.mask(-500, preserve_sign=True, blur_value=10)
        assert result < 0

    def test_zero_preserved(self):
        result = self.m.mask(0, preserve_zero=True)
        assert result == 0

    def test_blur_applied(self):
        original = 10000
        result = self.m.mask(original, blur_value=50, blur_type="percent")
        assert result != original


# ── LegalDetailsMasker ────────────────────────────────────────────────────────
class TestLegalDetailsMasker:
    def setup_method(self):
        self.m = LegalDetailsMasker()

    def test_returns_dict(self):
        result = self.m.mask(inn="7701234567")
        assert isinstance(result, dict)
        assert "full_name" in result
        assert "inn" in result

    def test_ul_detected_by_inn_10(self):
        result = self.m.mask(inn="7701234567")  # 10 цифр = ЮЛ
        assert "ООО" in result["full_name"] or "АО" in result["full_name"] or "ПАО" in result["full_name"]

    def test_ip_detected_by_inn_12(self):
        result = self.m.mask(inn="770912345601")  # 12 цифр = ИП
        assert "ИП" in result["full_name"] or "Индивидуальный" in result["full_name"]


if __name__ == "__main__":
    # Быстрый запуск без pytest
    import traceback
    tests_ok = 0
    tests_fail = 0
    for cls_name in ["TestBasicMasker", "TestFioMasker", "TestBirthdateMasker",
                     "TestInnMasker", "TestSnilsMasker", "TestEmailMasker",
                     "TestPhoneMasker", "TestBankCardMasker", "TestNumberMasker",
                     "TestLegalDetailsMasker"]:
        cls = globals()[cls_name]
        inst = cls()
        inst.setup_method()
        for method_name in [m for m in dir(cls) if m.startswith("test_")]:
            try:
                inst.setup_method()
                getattr(inst, method_name)()
                print(f"  ✓ {cls_name}.{method_name}")
                tests_ok += 1
            except Exception as e:
                print(f"  ✗ {cls_name}.{method_name}: {e}")
                tests_fail += 1
    print(f"\n{'='*50}")
    print(f"Passed: {tests_ok}, Failed: {tests_fail}")
