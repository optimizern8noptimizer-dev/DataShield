# DataShield BY 2.7.1 profile-driven runtime integration

Что изменено:
- runtime получил интеграцию explicit policy profiles;
- добавлен endpoint `GET /api/policy-profiles`;
- `analyze` и `mask` теперь принимают `profile_name` и `strict_mode`;
- `_discover_table_rules()` использует explicit profile first, затем fallback discovery;
- strict mode проверяет unmapped high-risk fields через `check_unmapped_high_risk`;
- generated config включает блок `policy`;
- UI позволяет выбрать policy profile и включить strict mode;
- в UI показывается runtime summary выбранной политики.

Что проверить:
1. login;
2. загрузить базу;
3. выбрать `banking_retail_by.yaml` или `banking_transactions_by.yaml`;
4. включить strict mode;
5. выполнить analyze;
6. выполнить mask;
7. проверить policy metadata в result summary и config.
