# DataShield BY v2.4.6 UI Syntax & Login Hotfix

Исправлено:
- SyntaxError в `ui.html`
- `login is not defined`
- сломанная JS-интерполяция ссылок Coverage JSON/CSV

Симптомы до фикса:
- кнопка "Войти в консоль" нажималась, но ничего не происходило
- в DevTools Console: `Unexpected token ';'` и `login is not defined`

Проверка:
1. Ctrl+F5 / InPrivate
2. открыть UI
3. нажать Login
4. проверить, что `POST /api/auth/login` уходит
5. после маскирования скачать базу / JSON / CSV
