from datashield.api.app import _discover_table_rules
from pathlib import Path


def _find_table(rules, name):
    return next(t for t in rules if t["name"] == name)


def test_cards_linked_fields_detected():
    db = Path(__file__).resolve().parents[1] / "demo_bank.sqlite"
    rules = _discover_table_rules(f"sqlite:///{db.as_posix()}")
    cards = _find_table(rules, "cards")
    pan = next(c for c in cards["columns"] if c["name"] == "pan")
    assert pan["service"] == "bankCard"
    assert "expiry" in pan.get("linked_columns", [])
    assert "holder_name" in pan.get("linked_columns", [])


def test_ids_not_discovered_as_maskable():
    db = Path(__file__).resolve().parents[1] / "demo_bank.sqlite"
    rules = _discover_table_rules(f"sqlite:///{db.as_posix()}")
    for table in rules:
        cols = {c["name"] for c in table["columns"]}
        assert "card_id" not in cols
        assert "client_id" not in cols
