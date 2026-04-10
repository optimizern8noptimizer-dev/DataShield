# DataShield BY 2.7.2 production validation pass

Что изменено:
- coverage report теперь включает production validation:
  - row_count_check
  - pk_stability
  - fk_integrity_check
  - pan_validation
  - iban_validation
  - distinct counts по маскированным колонкам
- strict mode теперь падает не только на unmapped high-risk, но и на:
  - pk mismatch
  - fk issues
  - invalid PAN results
  - invalid IBAN-like results
- UI показывает validation KPI в coverage summary.

Что проверить:
1. upload базы;
2. analyze;
3. выбрать profile + strict mode;
4. mask;
5. в coverage summary проверить:
   - Row count mismatches
   - PK mismatch tables
   - FK issues
   - Masked invalid PAN
   - Masked invalid IBAN
