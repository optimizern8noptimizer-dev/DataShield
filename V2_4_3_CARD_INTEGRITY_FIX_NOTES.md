# DataShield BY v2.4.3 Card Integrity Fix

Исправлено:
- `card_id` и все `*_id` / PK / FK колонки больше не попадают в auto-discovery и не маскируются
- `pan` обнаруживается только как явное поле карты, без ложного срабатывания на `card_id`
- `expiry` и `holder_name` продолжают обновляться как linked-fields к `pan`
- устранён дефект потери целостности карточной записи и изменения PK

Что перепроверить:
- `cards.card_id` не меняется
- `cards.pan` меняется в полный валидный номер
- `cards.expiry` меняется
- `cards.holder_name` меняется
- `cards.iban` меняется
