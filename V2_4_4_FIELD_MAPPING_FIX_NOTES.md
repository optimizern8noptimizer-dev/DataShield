# DataShield BY v2.4.4 Field Mapping & Card Completion Fix

Исправлено:
- `cards.expiry` -> явный `cardExpiry` masker
- `cards.holder_name` -> явный `cardHolder` masker
- `clients.national_id` -> `identifier` masker
- `legal_entities.tax_id` -> `taxId` masker
- `transactions.ip_address` -> `ipAddress` masker
- `transactions.merchant_city` -> `city` masker
- `transactions.device_id` -> `deviceId` masker
- `transactions.description` -> `text` masker
- `city` убран из address auto-discovery, чтобы города не превращались в адресные строки
- при маскировании `pan` pipeline теперь подтягивает связанные поля `expiry` и `holder_name` из исходной строки

Что перепроверить:
1. medium dataset: `cards`, `transactions`, `clients.national_id`, `legal_entities.tax_id`
2. `ip_address` должен оставаться IP, а не адресом
3. `merchant_city` должен оставаться городом, а не адресной строкой
