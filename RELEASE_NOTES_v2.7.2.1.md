# DataShield BY 2.7.2.1 Preview Endpoint Restore

Исправлено:
- восстановлены backend endpoints для table preview:
  - POST /api/databases/source-preview
  - POST /api/databases/masked-preview
- добавлен SQLite preview reader:
  - tables
  - columns
  - rows
  - preview_rows
  - total_rows

Что проверить:
1. login;
2. upload SQLite;
3. после загрузки — исходная таблица отображается в UI;
4. выполнить mask;
5. после маскирования — маскированная таблица отображается в UI.
