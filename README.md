<div align="center">

<img src="https://img.shields.io/badge/Python-3.10%2B%20%7C%203.15α-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLAlchemy-2.1-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white"/>
<img src="https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white"/>
<img src="https://img.shields.io/badge/PCI%20DSS-v4.0-00205B?style=for-the-badge"/>
<img src="https://img.shields.io/badge/GDPR-compliant-003399?style=for-the-badge"/>

<br/><br/>

```
 ██████╗  █████╗ ████████╗ █████╗     ███████╗██╗  ██╗██╗███████╗██╗     ██████╗
 ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗    ██╔════╝██║  ██║██║██╔════╝██║     ██╔══██╗
 ██║  ██║███████║   ██║   ███████║    ███████╗███████║██║█████╗  ██║     ██║  ██║
 ██║  ██║██╔══██║   ██║   ██╔══██║    ╚════██║██╔══██║██║██╔══╝  ██║     ██║  ██║
 ██████╔╝██║  ██║   ██║   ██║  ██║    ███████║██║  ██║██║███████╗███████╗██████╔╝
 ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝    ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═════╝
```

# DataShield BY

**Enterprise-платформа обезличивания банковских данных**

19 специализированных маскеров · FK-Safe ETL-движок · Web UI + RBAC · Audit hash-chain  
Беларусь-ориентированные профили · PCI DSS v4.0 · GDPR · 152-ФЗ

`v2.7.2.1-preview` · Python 3.10+ · Python 3.15α hotfix

[🚀 Быстрый старт](#-быстрый-старт) · [🎭 Маскеры](#-19-сервисов-маскирования) · [⚙️ Конфигурация](#-конфигурация) · [🔐 RBAC и аудит](#-rbac-и-аудит)

---

</div>

## Содержание

- [Что это и зачем](#-что-это-и-зачем)
- [Архитектура](#-архитектура)
- [19 сервисов маскирования](#-19-сервисов-маскирования)
- [Быстрый старт](#-быстрый-старт)
- [Конфигурация](#-конфигурация)
- [Политики и профили](#-политики-и-профили)
- [Режимы работы ETL](#-режимы-работы-etl)
- [Strict Mode](#-strict-mode)
- [RBAC и аудит](#-rbac-и-аудит)
- [Web UI](#-web-ui)
- [CLI](#-cli)
- [Поддерживаемые СУБД](#-поддерживаемые-субд)
- [Структура проекта](#-структура-проекта)
- [Стек технологий](#-стек-технологий)
- [Production checklist](#-production-checklist)

---

## 🎯 Что это и зачем

Передача реальных банковских данных в тестовые среды, аналитику или внешним подрядчикам — прямой путь к нарушению PCI DSS, GDPR и 152-ФЗ. **DataShield BY** решает эту задачу:

```
 Источник (prod БД)           DataShield BY                Приёмник (test БД)
 ──────────────────           ─────────────────────         ─────────────────────
                              ┌───────────────────┐
  Иванов Иван Иванович  ───► │  FIO Masker        │ ──►  Петров Сергей Алексеевич
  4111 1111 1111 1111   ───► │  BankCard Masker   │ ──►  4532 8765 4321 0987 (Luhn✓)
  +375 29 123-45-67     ───► │  Phone Masker      │ ──►  +375 (29) 876-54-32
  AB 1234567            ───► │  Passport Masker   │ ──►  AB 8765432
  123-456-789 01        ───► │  SNILS Masker      │ ──►  987-654-321 09
  BY64ALFA3001000000003  ──► │  BankAccount Masker│ ──►  BY17PRIO3001000000012
                              └───────────────────┘
```

**Ключевые свойства маскирования:**
- **Детерминированное** — одно входное значение всегда даёт одно выходное → ссылочная целостность сохраняется
- **Структурно-корректное** — PAN проходит Luhn, СНИЛС имеет верную контрольную сумму, IBAN валиден
- **FK-Safe** — таблицы обрабатываются в порядке топологической сортировки по внешним ключам
- **Согласованное** — ФИО в разных таблицах заменяется одинаково (household_key)

---

## 🏗 Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DataShield BY                               │
│                                                                     │
│  ┌──────────────┐    ┌─────────────────────────────────────────┐   │
│  │   Web UI     │    │              ETL Pipeline                │   │
│  │  (Flask SPA) │    │                                         │   │
│  │              │    │  Source DB ──► FK Graph ──► Topo Sort   │   │
│  │  Upload DB   │    │      │                        │          │   │
│  │  Run Job     │    │      └── batch_read ──► Maskers ──►     │   │
│  │  Download    │    │                           │              │   │
│  └──────┬───────┘    │                    target_write         │   │
│         │            │                           │              │   │
│  ┌──────▼───────┐    │                    AuditLog.jsonl       │   │
│  │ Control Plane│    └─────────────────────────────────────────┘   │
│  │  (SQLite /   │                                                   │
│  │  PostgreSQL) │    ┌──────────────────────────────────────────┐  │
│  │              │    │           19 Masking Services             │  │
│  │  RBAC/Auth   │    │  fio · birthdate · passport · snils      │  │
│  │  Job Queue   │    │  bankCard · bankAccount · phone · email  │  │
│  │  Audit Chain │    │  inn · legalDetails · address · ...      │  │
│  └──────────────┘    └──────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │   Worker     │    │         Policy Profiles                  │  │
│  │  (отдельный  │    │  banking_retail_by.yaml                  │  │
│  │   процесс)   │    │  banking_transactions_by.yaml            │  │
│  │  Poll + exec │    │  + кастомные профили                     │  │
│  └──────────────┘    └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎭 19 сервисов маскирования

Все маскеры поддерживают два режима: `deterministic` (SHA-256-сид, по умолчанию) и `randomized`.

### Персональные данные

| Сервис | Код | Что маскирует | Особенности |
|---|---|---|---|
| **ФИО** | `fio` | Фамилия, Имя, Отчество | Сохраняет пол, популярность имени, согласование внутри домохозяйства |
| **Дата рождения** | `birthdate` | Дата рождения | Сохраняет возрастную группу (<14, 14-18, 18+), корректно обрабатывает 29 февраля |
| **Паспорт** | `passport` | Серия, номер, дата выдачи, подразделение | Сохраняет регион в серии, подбирает реальный код подразделения ФМС |
| **СНИЛС** | `snils` | СНИЛС | Генерирует с верной контрольной суммой в формате `XXX-XXX-XXX YY` |
| **ИНН** | `inn` | ИНН ФЛ (12 цифр) и ЮЛ (10 цифр) | Сохраняет регион-префикс, верные контрольные разряды |
| **Место рождения** | `birthplace` | Адрес места рождения | Региональный профиль, синтетические адреса |
| **Водительское удостоверение** | `drivingLicense` | Серия, номер, даты, код ГИБДД | Сохраняет регион, срок действия относительно даты выдачи |

### Финансовые данные

| Сервис | Код | Что маскирует | Особенности |
|---|---|---|---|
| **Банковская карта** | `bankCard` | PAN, срок, держатель, CVV | Сохраняет BIN (первые 6 цифр), корректный алгоритм Луна |
| **Срок карты** | `cardExpiry` | MM/YY или MM/YYYY | Сохраняет валидность относительно текущей даты |
| **Держатель карты** | `cardHolder` | Имя на карте (латиница) | Транслитерационный маскинг |
| **Банковский счёт** | `bankAccount` | 20-значный счёт с БИК | Сохраняет балансовые счета (1-8 цифры), контрольный разряд с БИК |
| **Число / Сумма** | `number` | Финансовые суммы, остатки | Размытие на ±N% или ±N единиц, сохранение знака и нулей |

### Контактные данные и идентификаторы

| Сервис | Код | Что маскирует | Особенности |
|---|---|---|---|
| **Телефон** | `phone` | Телефон РБ (+375) и РФ (+7) | Сохраняет код оператора |
| **Email** | `email` | Email-адрес | Заменяет домен по типу: public / корпоративный / temp |
| **Адрес** | `cdiAddress` | Почтовый адрес | Региональный профиль, синтетические адреса BY/RU |
| **Юридическое лицо** | `legalDetails` | Название, ИНН, ОГРН, КПП | Автодетект ЮЛ/ИП по длине ИНН |
| **ПТС** | `vehiclePassport` | Документы ТС, VIN | Валидный VIN без букв I/O/Q, реальные марки/модели |

### Технические поля

| Сервис | Код | Что маскирует |
|---|---|---|
| **IP-адрес** | `ipAddress` | IPv4, сохраняет класс приватной сети |
| **Идентификатор устройства** | `deviceId` | Device ID, GUID |
| **Налоговый ID** | `taxId` | УНП, ОКПО, ИНН (общий) |
| **Город** | `city` | Город (профиль РБ: Минск, Гомель, Брест...) |
| **Регион** | `region` | Регион/область |
| **Дата/время** | `datetime` | ISO datetime, сдвиг на дни + минуты |
| **Текст** | `text` | Произвольный текст, посимвольно |
| **Базовый** | `basic` | Любая строка, посимвольно с сохранением класса символа |

---

## 🚀 Быстрый старт

### Docker (рекомендуется)

```bash
git clone https://github.com/your-username/datashield-by.git
cd datashield-by
docker-compose up --build -d
```

| Сервис | URL |
|---|---|
| Web UI | http://localhost:8080 |
| API Docs | http://localhost:8080/docs |

### Windows / Python 3.15α

```powershell
# Автоустановка (Python 3.15, SQLite, Waitress)
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_py315.ps1
.\scripts\start_all_windows.cmd
```

> Скрипт создаёт `.venv`, устанавливает зависимости с SQLAlchemy 2.1 (без greenlet), запускает `app` и `worker` в отдельных окнах.

### Локально (Python 3.10+)

```bash
cd datashield-by

python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\Activate.ps1    # Windows

pip install -e ".[postgres]"     # + psycopg для PostgreSQL
# pip install -e ".[oracle]"     # + oracledb для Oracle

# Настройка
cp .env.example .env
# Отредактировать .env

# Запуск Web UI
datashield-web

# Запуск воркера (в отдельном терминале)
datashield-worker
```

### Быстрый тест через CLI

```bash
# Маскировать демо-базу (dry run — без записи в приёмник)
datashield run --config config/example_config.yaml --mode dry_run

# Создать маскированную копию
datashield run --config config/example_config.yaml --mode copy

# Только указанные таблицы
datashield run --config config/example_config.yaml --tables clients,cards
```

---

## ⚙️ Конфигурация

Конфигурация задаётся в YAML-файле:

```yaml
version: "2.0"

session:
  name: "bank_prod_anonymize"
  mode: copy            # copy | in_place | dry_run | dump
  parallelism: 4        # параллельные потоки
  batch_size: 500       # строк за одну транзакцию
  snapshot_before: true # снапшот источника перед маскированием
  degraded_mode: char_mask  # fallback если маскер не определён

source:
  type: postgresql      # sqlite | postgresql | mysql | oracle
  host: prod-db.bank.local
  port: 5432
  database: bank_prod
  username: datashield_ro  # только чтение!
  password: ${DS_SOURCE_PASSWORD}

target:
  type: postgresql
  host: test-db.bank.local
  database: bank_test

cache:
  backend: memory       # memory | redis
  ttl: 2592000          # 30 дней (для детерминированности)

audit:
  log_path: ./logs/datashield_audit.jsonl
  strict_key: true      # требовать DATASHIELD_AUDIT_KEY из окружения

tables:
  - name: clients
    pk_column: client_id
    columns:
      - name: full_name
        service: fio
      - name: birth_date
        service: birthdate
      - name: phone
        service: phone
      - name: email
        service: email
      - name: address
        service: cdiAddress
      - name: income
        service: number
        params:
          blur_type: percent    # percent | units
          blur_value: 20        # ±20%
          preserve_sign: true
          preserve_zero: true

  - name: cards
    pk_column: card_id
    fk_columns:
      - name: client_id
        references: clients.client_id   # FK → будет обработана после clients
    columns:
      - name: card_number
        service: bankCard
      - name: account_number
        service: bankAccount
        params:
          bik: "044525225"      # БИК для контрольного разряда счёта

  - name: client_contacts
    pk_column: contact_id
    where_clause: "is_active = true"    # фильтрация строк
    columns:
      - name: contact_value
        service: dynamicContact         # автодетект phone/email по типу
        params:
          contact_type_column: contact_type
```

### Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `DS_CONTROL_DB_URL` | URL control-plane БД | `sqlite:///./datashield_control.db` |
| `DATASHIELD_AUDIT_KEY` | HMAC-ключ для подписи audit log | (сменить!) |
| `DS_WORKER_NAME` | Имя воркера в логах | hostname |
| `DS_WORKER_POLL_INTERVAL` | Интервал опроса очереди (сек) | `2` |
| `DS_SOURCE_PASSWORD` | Пароль источника (для подстановки в YAML) | — |

---

## 📋 Политики и профили

Политики позволяют централизованно задать маппинг колонок по имени — без перечисления в каждом конфиге:

```yaml
# datashield/policies/profiles/banking_retail_by.yaml
policy_name: banking_retail_by
policy_version: 1.0.0
country: BY
mode: explicit_profile_first

strict_policy:
  fail_on_unmapped_high_risk: true  # ошибка если высокорисковое поле не замаскировано
  fail_on_pk_change: true
  fail_on_fk_break: true
  fail_on_invalid_pan: true
  fail_on_invalid_iban: true

profiles:
  clients:
    first_name: fio
    last_name:  fio
    birth_date: birthdate
    passport_no: passport
    phone: phone
    email: email
    address: cdiAddress
  cards:
    pan:
      service: bankCard
      linked_columns: [expiry, holder_name]
    iban: bankAccount
```

**Встроенные профили:**

| Профиль | Описание |
|---|---|
| `banking_retail_by.yaml` | Розничный банкинг, Беларусь: клиенты, карты, счета, юрлица |
| `banking_transactions_by.yaml` | Транзакционные данные, платёжные документы |

```bash
# Использование профиля
datashield run --config config.yaml --policy banking_retail_by
```

---

## 🔄 Режимы работы ETL

| Режим | Описание | Когда использовать |
|---|---|---|
| `dry_run` | Маскирование без записи, только статистика | Проверка конфига, оценка покрытия |
| `copy` | Читает из источника, пишет в приёмник | **Основной режим** для тестовых сред |
| `in_place` | Маскирование на месте в источнике | Архивирование, когда prod-копия ненужна |
| `dump` | Выгрузка в файл (SQL/CSV) | Передача подрядчикам |

**FK-Safe порядок обработки:**

ETL-движок автоматически строит граф внешних ключей и обрабатывает таблицы в порядке топологической сортировки. Детерминированный маскер гарантирует, что `client_id = 12345` в таблице `clients` и `client_id = 12345` в таблице `cards` будут заменены одним и тем же значением.

---

## 🚨 Strict Mode

Strict Mode запрещает запуск маскирования если обнаружены нарушения:

```python
# Включается в политике или явно
strict = StrictModeSettings(
    fail_on_unmapped_high_risk=True,  # высокорисковые поля должны быть замаскированы
    fail_on_pk_change=True,           # PK не должны меняться
    fail_on_fk_break=True,            # ссылочная целостность должна сохраняться
    fail_on_invalid_pan=True,         # PAN должны проходить алгоритм Луна
    fail_on_invalid_iban=True,        # IBAN должны быть структурно корректны
)
```

**Auto-discovery** — автоматическое определение типа данных по имени колонки:

```
pan, card_number, masked_pan  → bankCard
email, mail, почта             → email
phone, mobile, msisdn          → phone
birth_date, dob, birthday      → birthdate
passport, passport_no          → passport
iban, account_number           → bankAccount
amount, balance, salary        → number
ip_address, src_ip             → ipAddress
```

---

## 🔐 RBAC и аудит

### Роли пользователей

| Роль | Уровень | Права |
|---|---|---|
| `viewer` | 10 | Просмотр логов, статистики, списка заданий |
| `operator` | 20 | + запуск заданий маскирования, загрузка БД |
| `security_officer` | 25 | + управление правилами, верификация аудита |
| `admin` | 30 | Полный доступ, управление пользователями |

### Audit Hash-Chain

Каждая запись в `datashield_audit.jsonl` подписана HMAC-SHA256:

```json
{
  "payload": {
    "event": "session_complete",
    "session_id": "uuid-...",
    "timestamp": "2025-01-15T10:30:00",
    "tables": [{"table": "clients", "rows_processed": 15420, "rows_masked": 15420}],
    "total_rows": 15420
  },
  "sig": "a3f8c2d1e9b7..."
}
```

```bash
# Верификация целостности audit log
datashield verify-audit --log ./logs/datashield_audit.jsonl
```

Нарушение подписи или пропуск записи — автоматически обнаруживается.

---

## 🖥 Web UI

Веб-интерфейс доступен на `http://localhost:8080` после запуска.

**Основной сценарий работы:**

```
1. Войти в систему (RBAC)
        │
2. Загрузить SQLite-базу  [POST /api/databases/upload]
        │
3. Нажать «Запустить маскирование»  [POST /api/databases/mask]
        │           ├── auto-discovery колонок
        │           ├── генерация YAML-конфига → storage/configs/
        │           └── постановка job в очередь
        │
4. Дождаться завершения (polling статуса)
        │
5. Скачать маскированную базу  [GET /api/databases/download/<file>]
```

**API endpoints Web UI:**

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/auth/login` | Аутентификация, получение токена |
| `POST` | `/api/auth/logout` | Отзыв токена |
| `GET` | `/api/databases` | Список загруженных баз |
| `POST` | `/api/databases/upload` | Загрузка SQLite (.db/.sqlite/.sqlite3) |
| `POST` | `/api/databases/mask` | Запуск маскирования (постановка в очередь) |
| `GET` | `/api/databases/download/<file>` | Скачать маскированную базу |
| `GET` | `/api/jobs` | Список заданий |
| `GET` | `/api/jobs/<id>` | Статус задания |
| `GET` | `/api/audit` | Просмотр audit log |
| `GET` | `/api/audit/verify` | Верификация hash-chain |
| `GET` | `/api/services` | Список доступных маскеров |
| `GET` | `/api/policies` | Список доступных профилей политик |

---

## 🖥 CLI

```bash
# Запустить маскирование
datashield run \
  --config config/example_config.yaml \
  --mode copy \
  --tables clients,cards,transactions \
  --verbose

# Миграция схемы control-plane
datashield-migrate

# Запуск Web UI
datashield-web

# Запуск воркера
datashield-worker
```

---

## 🗄 Поддерживаемые СУБД

| СУБД | Установка | Примечание |
|---|---|---|
| **SQLite** | Встроена | Режим разработки и Windows hotfix |
| **PostgreSQL** | `pip install -e ".[postgres]"` | Рекомендуется для production |
| **MySQL / MariaDB** | `pymysql` (уже в зависимостях) | |
| **Oracle** | `pip install -e ".[oracle]"` | oracledb 2.0+ |

**Control-plane** (пользователи, задания, аудит) работает на SQLite по умолчанию. Для production рекомендуется перевести на PostgreSQL через `DS_CONTROL_DB_URL`.

---

## 📁 Структура проекта

```
datashield-by/
│
├── datashield/                     # Основной пакет
│   ├── api/
│   │   ├── app.py                  # Flask Web UI + REST API (Waitress WSGI)
│   │   └── ui.html                 # Single-page Web UI
│   │
│   ├── maskers/
│   │   ├── base.py                 # BaseMasker: детерминированный RNG, кэш, посимвольный маскинг
│   │   └── services.py             # 19 сервисов маскирования
│   │
│   ├── etl/
│   │   ├── pipeline.py             # ETL-движок: batch read → mask → write, статистика
│   │   └── fk_graph.py             # FK-граф и топологическая сортировка таблиц
│   │
│   ├── services/
│   │   ├── policy_loader.py        # Загрузка YAML-профилей политик
│   │   ├── strict_mode.py          # Strict Mode: проверки PAN/IBAN/PK/FK
│   │   └── validators.py           # Валидация PAN (Luhn), IBAN
│   │
│   ├── policies/profiles/
│   │   ├── banking_retail_by.yaml      # Профиль: розничный банкинг BY
│   │   └── banking_transactions_by.yaml # Профиль: транзакционные данные BY
│   │
│   ├── audit/__init__.py           # Append-only audit log с HMAC-SHA256
│   ├── cache/__init__.py           # Memory / Redis кэш
│   ├── controlplane.py             # RBAC, Job Queue, Auth Tokens (SQLAlchemy ORM)
│   ├── worker.py                   # Воркер: poll → claim → execute → heartbeat
│   ├── cli.py                      # Click CLI: run, verify-audit
│   ├── migrate.py                  # Миграция control-plane схемы
│   └── dictionaries/__init__.py    # Словари: ФИО, адреса, юрлица, банки BY/RU
│
├── config/
│   └── example_config.yaml         # Пример конфигурации маскирования
│
├── scripts/
│   ├── bootstrap_windows_py315.ps1 # Автоустановка для Windows + Python 3.15α
│   └── start_all_windows.cmd       # Запуск app + worker (Windows)
│
├── docker-compose.yml
├── .env.example
├── .env.windows.example
└── INSTALL_WINDOWS_PY315.md
```

---

## 🔧 Стек технологий

| Компонент | Технология |
|---|---|
| **Backend** | Python 3.10+ (совместим с 3.15α) |
| **Web Framework** | Flask 3.0 |
| **WSGI** | Waitress (Windows-friendly, без компилируемых зависимостей) |
| **ORM** | SQLAlchemy 2.1 (greenlet-free для Python 3.15α) |
| **Control DB** | SQLite (dev) / PostgreSQL (prod) |
| **Кэш** | In-memory / Redis |
| **Аудит** | Append-only JSONL с HMAC-SHA256 |
| **CLI** | Click 8.1 |
| **Конфигурация** | PyYAML |
| **Деплой** | Docker + docker-compose / Windows scripts |

---

## ✅ Production checklist

```
Безопасность
  [ ] Сменить DATASHIELD_AUDIT_KEY (по умолчанию — sentinel-значение)
  [ ] Использовать read-only пользователя для подключения к источнику
  [ ] Установить strict_key: true в конфиге audit
  [ ] Ограничить сетевой доступ к Web UI (nginx/VPN)
  [ ] Проверить .env не попал в git (добавлен в .gitignore)

База данных
  [ ] Перевести control-plane на PostgreSQL
      DS_CONTROL_DB_URL=postgresql+psycopg://user:pass@host/datashield_ctrl
  [ ] Настроить бэкапы control-plane и audit log
  [ ] Использовать отдельные credentials для source и target БД

Масккирование
  [ ] Включить Strict Mode для production-конфигов
  [ ] Проверить покрытие всех высокорисковых полей через dry_run
  [ ] Верифицировать PAN (Luhn) и IBAN в результатах
  [ ] Настроить redis-кэш для детерминированности между сессиями
      cache.backend: redis

Инфраструктура
  [ ] Запустить app и worker как отдельные systemd-сервисы
  [ ] Настроить ротацию audit.jsonl
  [ ] Подключить мониторинг (Prometheus / Grafana)
  [ ] Провести нагрузочное тестирование с реальным объёмом

Комплаенс
  [ ] Задокументировать перечень маскируемых полей для регулятора
  [ ] Проверить соответствие НБРБ СТБ 34.101.72 (обезличивание)
  [ ] Настроить периодическую верификацию hash-chain audit log
  [ ] Хранить audit log не менее 5 лет (требование НБ РБ)
```

---

## 📄 Лицензия

Proprietary — DataShield BY 2.7.x. Использование регулируется коммерческим лицензионным соглашением.

---

<div align="center">

**DataShield BY** · Flask · SQLAlchemy · 19 Maskers · FK-Safe ETL · Audit Hash-Chain

*Enterprise обезличивание банковских данных — структурно корректно, детерминированно, аудитируемо*

</div>
