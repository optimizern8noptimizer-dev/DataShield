# DataShield BY v2.4.8 UI Null-Safe Fix

Исправления:
- добавлены отсутствующие HTML-элементы для блока анализа покрытия;
- все критичные обращения к DOM переведены в null-safe режим;
- `setOutput`, `setStatusState`, `setSession`, `renderDetectedColumnsTable` больше не падают на `null`;
- исправлено падение после маскирования на `classList` при отсутствии coverage/result блоков.

Что проверить:
1. загрузить SQLite базу;
2. нажать «Анализ покрытия»;
3. убедиться, что появляется таблица найденных полей;
4. запустить маскирование;
5. убедиться, что UI не падает с `Cannot read properties of null (reading 'classList')`.
