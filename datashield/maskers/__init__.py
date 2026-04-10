"""Реестр сервисов маскирования и фабрика."""
from __future__ import annotations
from .services import (
    BasicMasker, FioMasker, BirthdateMasker, InnMasker, SnilsMasker,
    BirthplaceMasker, BankCardMasker, PassportMasker, DrivingLicenseMasker,
    LegalDetailsMasker, AddressMasker, BankAccountMasker,
    PhoneMasker, SimplePhoneMasker, EmailMasker,
    VehiclePassportMasker, IdentifierMasker, TaxIdMasker, CityMasker, IpAddressMasker, DeviceIdMasker, TextMasker, CardExpiryMasker, CardHolderMasker, DynamicContactMasker, RegionMasker, DateTimeMasker, NumberMasker,
)
from .base import BaseMasker

_REGISTRY: dict[str, type[BaseMasker]] = {
    "basic": BasicMasker,
    "fio": FioMasker,
    "birthdate": BirthdateMasker,
    "inn": InnMasker,
    "snils": SnilsMasker,
    "birthplace": BirthplaceMasker,
    "bankCard": BankCardMasker,
    "bankCardDefault": BankCardMasker,
    "passport": PassportMasker,
    "drivingLicense": DrivingLicenseMasker,
    "legalDetails": LegalDetailsMasker,
    "cdiAddress": AddressMasker,
    "rawAddress": AddressMasker,
    "bankAccount": BankAccountMasker,
    "phone": PhoneMasker,
    "simple_phone": SimplePhoneMasker,
    "email": EmailMasker,
    "vehiclePassport": VehiclePassportMasker,
    "identifier": IdentifierMasker,
    "taxId": TaxIdMasker,
    "city": CityMasker,
    "ipAddress": IpAddressMasker,
    "deviceId": DeviceIdMasker,
    "text": TextMasker,
    "cardExpiry": CardExpiryMasker,
    "cardHolder": CardHolderMasker,
    "dynamicContact": DynamicContactMasker,
    "region": RegionMasker,
    "datetime": DateTimeMasker,
    "number": NumberMasker,
}


def get_masker(service: str, cache=None, mode: str = "deterministic") -> BaseMasker:
    cls = _REGISTRY.get(service)
    if cls is None:
        raise ValueError(f"Неизвестный сервис маскирования: '{service}'. "
                         f"Доступные: {list(_REGISTRY.keys())}")
    return cls(cache=cache, mode=mode)


def list_services() -> list[str]:
    return sorted(_REGISTRY.keys())
