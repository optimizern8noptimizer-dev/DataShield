# DataShield BY 2.3.2 — Masking Fix Pack

## Что исправлено

На основании сравнения исходной и маскированных тестовых SQLite-баз были выявлены и исправлены следующие проблемы:

- `clients.passport_no` не маскировался
- `clients.national_id` не маскировался
- `legal_entities.registration_no` не маскировался
- `legal_entities.tax_id` не маскировался
- `client_contacts.contact_value` не маскировался, потому что тип контакта хранился в соседней колонке `contact_type`
- `clients.region` не маскировался
- `clients.created_at` не маскировался

## Что изменено в коде

1. Улучшен auto-discovery колонок и добавлен data-profiling по sample values.
2. Добавлен `dynamicContact` masker для полей типа `contact_value` с маршрутизацией по `contact_type`.
3. Добавлен `region` masker для замены региона.
4. Добавлен `datetime` masker для ISO timestamp полей (`created_at`, `updated_at`, `timestamp`).
5. `passport` masker теперь умеет маскировать scalar values вроде `passport_no` и `national_id`, а не только составные структуры.
6. Pipeline обновлён так, чтобы dict-result мог обновлять связанные поля в той же строке.

## Что проверить после обновления

1. Загрузить `bank_demo_small.sqlite`
2. Выполнить маскирование
3. Проверить, что изменяются:
   - `passport_no`
   - `national_id`
   - `registration_no`
   - `tax_id`
   - `contact_value`
   - `region`
   - `created_at`
4. Убедиться, что FK и структура таблиц сохраняются
