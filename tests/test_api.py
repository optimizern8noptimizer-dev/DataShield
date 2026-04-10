import os

os.environ['DATASHIELD_API_TOKEN'] = 'testtoken'
os.environ['DATASHIELD_AUDIT_KEY'] = 'abcdefghijklmnopqrstuvwxyz123456'

from datashield.api.app import app

client = app.test_client()


def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_mask_requires_token():
    r = client.post('/api/mask', json={'service': 'basic', 'value': 'abc'})
    assert r.status_code == 401


def test_mask_with_token():
    r = client.post('/api/mask', headers={'Authorization': 'Bearer testtoken'}, json={'service': 'phone', 'value': '+375 (29) 123-45-67'})
    assert r.status_code == 200
    assert r.get_json()['masked'].startswith('+375')


import sqlite3
from datashield.api.app import _discover_table_rules


def test_discovery_skips_ids_and_links_pan(tmp_path):
    db = tmp_path / "demo.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE clients (
        client_id INTEGER PRIMARY KEY,
        first_name TEXT
    );
    CREATE TABLE cards (
        card_id INTEGER PRIMARY KEY,
        client_id INTEGER NOT NULL,
        pan TEXT NOT NULL,
        expiry TEXT,
        holder_name TEXT,
        iban TEXT,
        FOREIGN KEY(client_id) REFERENCES clients(client_id)
    );
    INSERT INTO clients VALUES (1, 'A');
    INSERT INTO cards VALUES (1, 1, '4111111111111111', '12/29', 'ANDREY SOKOLOV', 'BY13NBRB3600900000002Z00AB00');
    """)
    con.commit()
    con.close()

    rules = _discover_table_rules(f"sqlite:///{db.as_posix()}")
    cards_rule = next(r for r in rules if r["name"] == "cards")
    names = {c["name"]: c for c in cards_rule["columns"]}
    assert "card_id" not in names
    assert "client_id" not in names
    assert names["pan"]["service"] == "bankCard"
    assert set(names["pan"].get("linked_columns", [])) == {"expiry", "holder_name"}
