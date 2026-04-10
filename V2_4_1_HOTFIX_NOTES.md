# DataShield BY v2.4.1 Coverage Hotfix

Исправлен дефект формирования coverage CSV/JSON report:

- ошибка `sequence item 0: expected str instance, tuple found`
- безопасная обработка `tuple` в `linked_results`
- безопасное CSV-экранирование всех полей отчёта

Что проверить:
1. загрузка SQLite БД
2. запуск маскирования
3. отсутствие ошибки в UI
4. появление report JSON/CSV
5. путь к маскированной БД и report links
