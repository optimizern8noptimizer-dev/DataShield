import os

os.environ['DS_CONTROL_DB_URL'] = 'sqlite:///./test_controlplane.db'
os.environ['DS_BOOTSTRAP_ADMIN'] = 'admin'
os.environ['DS_BOOTSTRAP_PASSWORD'] = 'admin12345'

from datashield.api.app import app
from datashield.controlplane import init_db

init_db()
client = app.test_client()


def get_admin_token():
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin12345'})
    assert r.status_code == 200
    return r.get_json()['token']


def test_login_and_me():
    token = get_admin_token()
    r = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['role'] == 'admin'


def test_create_user_and_list():
    token = get_admin_token()
    r = client.post('/api/users', headers={'Authorization': f'Bearer {token}'}, json={'username': 'op1', 'password': 'StrongPass123', 'role': 'operator', 'is_active': True})
    assert r.status_code in (200, 400)
    r = client.get('/api/users', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert any(u['username'] == 'admin' for u in r.get_json())
