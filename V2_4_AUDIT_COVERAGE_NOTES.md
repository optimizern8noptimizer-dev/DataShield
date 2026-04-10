# DataShield BY v2.4 Audit & Coverage Report

## Что добавлено
- экран **Audit & Coverage Report** в Web UI;
- предварительный анализ загруженной SQLite-БД перед маскированием;
- post-mask coverage report после выполнения job;
- экспорт coverage report в **JSON** и **CSV**;
- API:
  - `POST /api/databases/analyze`
  - `GET /api/reports/<job_id>`
  - `GET /api/reports/download/<filename>`

## Что показывает отчёт
- сколько чувствительных колонок найдено;
- сколько реально изменилось после маскирования;
- сколько осталось без изменений;
- high-risk / medium-risk unmasked;
- детализацию по таблицам и колонкам.

## Как проверить
1. Войти в UI.
2. Загрузить SQLite базу.
3. Нажать **Анализ покрытия**.
4. Запустить маскирование.
5. Проверить блок **Audit & Coverage Report**.
6. Скачать JSON и CSV отчёты.

## Важное
- Отчёт формируется для upload-flow SQLite.
- Исходная база не меняется; сравнение делается между source copy и masked copy.
- Для enterprise DBMS (PostgreSQL/MySQL/Oracle) потребуется отдельный connector-aware report engine.
