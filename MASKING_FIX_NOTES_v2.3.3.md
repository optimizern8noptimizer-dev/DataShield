# DataShield BY 2.3.3 Card+Date Fix

Исправлено:
- `cards.pan` теперь обнаруживается и маскируется через `bankCard` с linked-columns
- `cards.expiry` теперь маскируется как связанное поле к `pan`
- `cards.holder_name` теперь маскируется как связанное поле к `pan`
- `cards.iban` продолжает маскироваться отдельным `bankAccount` правилом
- `birth_date` на `29 Feb` больше не остаётся исходным из-за безопасной замены года

Что перепроверить:
- `cards.pan`
- `cards.expiry`
- `cards.holder_name`
- `cards.iban`
- `clients.birth_date` для `1988-02-29`
