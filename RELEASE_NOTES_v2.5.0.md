# DataShield BY 2.5.0 Consolidated Clean Build

Что сделано:
- полностью консолидирован UI: один согласованный `ui.html` без цепочки конфликтующих hotfix-вставок;
- весь JS собран в один согласованный inline-script;
- все DOM-обращения null-safe;
- согласованы flows: login / upload / analyze / mask / report / download;
- cleaned distribution: удалены runtime DB, logs, pycache, pytest cache.

Что проверить:
1. login;
2. upload SQLite;
3. analyze coverage;
4. run masking;
5. report render;
6. download masked DB and reports.
