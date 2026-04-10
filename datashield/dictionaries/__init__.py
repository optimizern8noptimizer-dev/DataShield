"""Belarus-oriented synthetic dictionaries for DataShield BY 2.0.

Service compatibility with v1.x is preserved by keeping the same exported names.
The dictionaries are synthetic and intended for anonymization only.
"""
from __future__ import annotations

import random

# first_name, gender, popularity(1-5)
FIRST_NAMES = [
    ("Александр", "M", 1), ("Дмитрий", "M", 1), ("Сергей", "M", 1),
    ("Андрей", "M", 1), ("Иван", "M", 2), ("Павел", "M", 2),
    ("Егор", "M", 3), ("Максим", "M", 2), ("Артём", "M", 2),
    ("Никита", "M", 3), ("Руслан", "M", 3), ("Кирилл", "M", 3),
    ("Евгений", "M", 2), ("Владислав", "M", 3), ("Антон", "M", 3),
    ("Анна", "F", 1), ("Мария", "F", 1), ("Екатерина", "F", 1),
    ("Ольга", "F", 2), ("Елена", "F", 2), ("Наталья", "F", 2),
    ("Алина", "F", 3), ("Дарья", "F", 2), ("Ксения", "F", 3),
    ("Виктория", "F", 2), ("Татьяна", "F", 3), ("Юлия", "F", 2),
    ("Полина", "F", 3), ("Вероника", "F", 4), ("Анастасия", "F", 1),
]

PATRONYMICS = [
    ("Александрович", "M", 1), ("Сергеевич", "M", 1), ("Дмитриевич", "M", 1),
    ("Андреевич", "M", 2), ("Иванович", "M", 2), ("Павлович", "M", 3),
    ("Александровна", "F", 1), ("Сергеевна", "F", 1), ("Дмитриевна", "F", 1),
    ("Андреевна", "F", 2), ("Ивановна", "F", 2), ("Павловна", "F", 3),
]

# male, female, popularity, paired
LAST_NAMES = [
    ("Иванов", "Иванова", 1, True), ("Петров", "Петрова", 1, True),
    ("Сидоров", "Сидорова", 1, True), ("Козлов", "Козлова", 2, True),
    ("Морозов", "Морозова", 2, True), ("Новиков", "Новикова", 2, True),
    ("Васильев", "Васильева", 2, True), ("Ковалёв", "Ковалёва", 2, True),
    ("Михайлов", "Михайлова", 2, True), ("Николаев", "Николаева", 3, True),
    ("Лебедев", "Лебедева", 3, True), ("Зайцев", "Зайцева", 3, True),
    ("Романов", "Романова", 3, True), ("Орлов", "Орлова", 3, True),
    ("Макаров", "Макарова", 3, True), ("Климов", "Климова", 4, True),
    ("Тарасенко", "Тарасенко", 3, False), ("Коваль", "Коваль", 2, False),
    ("Жук", "Жук", 3, False), ("Черных", "Черных", 4, False),
]

REGIONS = {
    "MN": {"name": "г. Минск", "code": "MN", "district": "Минск"},
    "BR": {"name": "Брестская область", "code": "BR", "district": "Брест"},
    "VI": {"name": "Витебская область", "code": "VI", "district": "Витебск"},
    "HO": {"name": "Гомельская область", "code": "HO", "district": "Гомель"},
    "HR": {"name": "Гродненская область", "code": "HR", "district": "Гродно"},
    "MI": {"name": "Минская область", "code": "MI", "district": "Минск"},
    "MO": {"name": "Могилевская область", "code": "MO", "district": "Могилев"},
}

SYNTHETIC_ADDRESSES = {
    "MN": [
        {"city": "Минск", "street": "пр-т Победителей", "house": "7"},
        {"city": "Минск", "street": "ул. Немига", "house": "12"},
        {"city": "Минск", "street": "ул. Притыцкого", "house": "34"},
        {"city": "Минск", "street": "ул. Сурганова", "house": "15"},
    ],
    "BR": [
        {"city": "Брест", "street": "ул. Советская", "house": "18"},
        {"city": "Брест", "street": "ул. Московская", "house": "142"},
    ],
    "VI": [
        {"city": "Витебск", "street": "пр-т Строителей", "house": "9"},
        {"city": "Витебск", "street": "ул. Ленина", "house": "44"},
    ],
    "HO": [
        {"city": "Гомель", "street": "ул. Советская", "house": "29"},
        {"city": "Гомель", "street": "пр-т Ленина", "house": "3"},
    ],
    "HR": [
        {"city": "Гродно", "street": "ул. Горького", "house": "91"},
        {"city": "Гродно", "street": "ул. Социалистическая", "house": "37"},
    ],
    "MI": [
        {"city": "Борисов", "street": "ул. Гагарина", "house": "62"},
        {"city": "Солигорск", "street": "ул. Ленина", "house": "21"},
    ],
    "MO": [
        {"city": "Могилев", "street": "ул. Первомайская", "house": "31"},
        {"city": "Могилев", "street": "пр-т Мира", "house": "8"},
    ],
    "default": [
        {"city": "Центральный", "street": "ул. Центральная", "house": "1"},
        {"city": "Озерный", "street": "ул. Молодежная", "house": "5"},
    ],
}

PUBLIC_DOMAINS = [
    "gmail.com", "yandex.by", "yandex.ru", "mail.ru", "tut.by", "outlook.com"
]
CORPORATE_DOMAINS = [
    "bank.local", "corp.by", "finance.by", "holding.by", "enterprise.local"
]
TEMP_DOMAINS = [
    "tempmail.com", "mailinator.com", "guerrillamail.com"
]

VEHICLE_BRANDS = {
    "Geely": ["Coolray", "Atlas", "Emgrand"],
    "Volkswagen": ["Polo", "Passat", "Tiguan"],
    "Renault": ["Logan", "Duster", "Sandero"],
    "LADA": ["Vesta", "Granta", "Niva"],
    "BMW": ["X5", "3 Series", "5 Series"],
    "Audi": ["A4", "A6", "Q5"],
}

LEGAL_ENTITIES = [
    {"type": "ЮЛ", "full_name": 'ООО "БелФинТех"', "short_name": 'ООО "БелФинТех"', "inn": "190123456", "ogrn": "192345678", "kpp": None},
    {"type": "ЮЛ", "full_name": 'ЗАО "Доверие Банк Сервис"', "short_name": 'ЗАО "Доверие Банк Сервис"', "inn": "191234567", "ogrn": "193456789", "kpp": None},
    {"type": "ЮЛ", "full_name": 'ОАО "Платежные решения"', "short_name": 'ОАО "Платежные решения"', "inn": "192345678", "ogrn": "194567890", "kpp": None},
    {"type": "ИП", "full_name": 'ИП Коваль А.В.', "short_name": None, "inn": "290123456", "ogrn": "495678901", "kpp": None},
    {"type": "ИП", "full_name": 'ИП Романова Е.С.', "short_name": None, "inn": "291234567", "ogrn": "496789012", "kpp": None},
]

GIBDD_REGIONS = {
    "MN": ["МРЭО Минск-1", "МРЭО Минск-2"],
    "BR": ["МРЭО Брест-1"],
    "default": ["МРЭО-01", "МРЭО-02"],
}

FMS_UNITS = {
    "MN": [{"code": "MN-001", "name": "Отдел по гражданству и миграции Минск-1"}],
    "BR": [{"code": "BR-001", "name": "Отдел по гражданству и миграции Брест-1"}],
    "default": [{"code": "BY-001", "name": "Отдел по гражданству и миграции"}],
}


def get_names_by_gender_and_popularity(name_type: str, gender: str, popularity: int, exclude: str | None = None) -> str:
    if name_type == "first":
        pool = [n for n, g, p in FIRST_NAMES if g == gender and abs(p - popularity) <= 1 and n != exclude]
    elif name_type == "patronymic":
        pool = [n for n, g, p in PATRONYMICS if g == gender and abs(p - popularity) <= 1 and n != exclude]
    else:
        if gender == "M":
            pool = [m for m, _, p, _ in LAST_NAMES if abs(p - popularity) <= 1 and m != exclude]
        else:
            pool = [f for _, f, p, _ in LAST_NAMES if abs(p - popularity) <= 1 and f != exclude]
    if not pool:
        if name_type == "first":
            pool = [n for n, g, _ in FIRST_NAMES if g == gender and n != exclude]
        elif name_type == "patronymic":
            pool = [n for n, g, _ in PATRONYMICS if g == gender and n != exclude]
        else:
            if gender == "M":
                pool = [m for m, _, _, _ in LAST_NAMES if m != exclude]
            else:
                pool = [f for _, f, _, _ in LAST_NAMES if f != exclude]
    return random.choice(pool) if pool else exclude or "Тестов"


def get_last_name_info(last_name: str) -> dict | None:
    for male, female, popularity, paired in LAST_NAMES:
        if last_name in (male, female):
            return {
                "male": male,
                "female": female,
                "popularity": popularity,
                "paired": paired,
                "gender": "M" if last_name == male else "F",
            }
    return None


def get_paired_last_name(last_name: str, target_gender: str) -> str | None:
    info = get_last_name_info(last_name)
    if not info:
        return None
    return info["male"] if target_gender == "M" else info["female"]
