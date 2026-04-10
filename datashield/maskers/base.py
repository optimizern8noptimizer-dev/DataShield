"""Базовый класс для всех сервисов маскирования."""
from __future__ import annotations
import random
import hashlib
from abc import ABC, abstractmethod
from typing import Any


class BaseMasker(ABC):
    """Базовый сервис маскирования с поддержкой детерминированного режима."""

    service_name: str = "base"

    # Кириллические гласные/согласные
    CYR_VOWELS = "аеёиоуыьъэюя"
    CYR_VOWELS_UPPER = "АЕЁИОУЫЬЪЭЮЯ"
    CYR_CONSONANTS = "бвгджзйклмнпрстфхцчшщ"
    CYR_CONSONANTS_UPPER = "БВГДЖЗЙКЛМНПРСТФХЦЧШЩ"

    # Латинские гласные/согласные
    LAT_VOWELS = "aeiou"
    LAT_VOWELS_UPPER = "AEIOU"
    LAT_CONSONANTS = "bcdfghjklmnpqrstvwxyz"
    LAT_CONSONANTS_UPPER = "BCDFGHJKLMNPQRSTVWXYZ"

    DIGITS = "0123456789"

    def __init__(self, cache=None, mode: str = "deterministic"):
        self._cache = cache
        self._mode = mode  # deterministic | randomized

    def _seed_from_input(self, value: str) -> random.Random:
        """Детерминированный Random из входного значения."""
        seed = int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)
        return random.Random(seed)

    def _rnd(self, input_val: str = "") -> random.Random:
        """Вернуть Random: детерминированный или случайный."""
        if self._mode == "deterministic" and input_val:
            return self._seed_from_input(f"{self.service_name}:{input_val}")
        return random.Random()

    def mask_with_cache(self, key: str, fn, *args) -> Any:
        """Маскировать с кэшированием результата."""
        if self._cache is None:
            return fn(*args)
        cache_key = self._cache.make_key(self.service_name, key)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = fn(*args)
        self._cache.set(cache_key, result)
        return result

    @abstractmethod
    def mask(self, value: Any, **kwargs) -> Any:
        """Замаскировать значение."""
        ...

    def _pick_different(self, alphabet: str, current: str, rnd: random.Random) -> str:
        if len(alphabet) <= 1:
            return current
        options = [c for c in alphabet if c != current]
        return rnd.choice(options) if options else current

    def basic_mask_string(self, s: str, rnd: random.Random | None = None) -> str:
        """Mask each character while keeping character class and avoiding identity substitution when possible."""
        if rnd is None:
            rnd = self._rnd(s)
        result = []
        for ch in s:
            if ch in self.DIGITS:
                result.append(self._pick_different(self.DIGITS, ch, rnd))
            elif ch in self.CYR_VOWELS:
                result.append(self._pick_different(self.CYR_VOWELS, ch, rnd))
            elif ch in self.CYR_VOWELS_UPPER:
                result.append(self._pick_different(self.CYR_VOWELS_UPPER, ch, rnd))
            elif ch in self.CYR_CONSONANTS:
                result.append(self._pick_different(self.CYR_CONSONANTS, ch, rnd))
            elif ch in self.CYR_CONSONANTS_UPPER:
                result.append(self._pick_different(self.CYR_CONSONANTS_UPPER, ch, rnd))
            elif ch in self.LAT_VOWELS:
                result.append(self._pick_different(self.LAT_VOWELS, ch, rnd))
            elif ch in self.LAT_VOWELS_UPPER:
                result.append(self._pick_different(self.LAT_VOWELS_UPPER, ch, rnd))
            elif ch in self.LAT_CONSONANTS:
                result.append(self._pick_different(self.LAT_CONSONANTS, ch, rnd))
            elif ch in self.LAT_CONSONANTS_UPPER:
                result.append(self._pick_different(self.LAT_CONSONANTS_UPPER, ch, rnd))
            else:
                result.append(ch)
        return "".join(result)
