import os
import uuid
from pathlib import Path

DB_PATH = Path('./test_controlplane_v22.db')
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ['DS_CONTROL_DB_URL'] = f'sqlite:///{DB_PATH}'
os.environ['DS_BOOTSTRAP_ADMIN'] = 'admin'
os.environ['DS_BOOTSTRAP_PASSWORD'] = 'admin12345'
os.environ['DATASHIELD_AUDIT_KEY'] = 'abcdefghijklmnopqrstuvwxyz123456'

from datashield.api.app import app
from datashield.controlplane import init_db
from datashield.worker import run_once

init_db()
client = app.test_client()


def admin_token():
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin12345'})
    assert r.status_code == 200
    return r.get_json()['token']


def test_queue_stats_and_worker_execution():
    token = admin_token()
    headers = {'Authorization': f'Bearer {token}'}
    r = client.post('/api/jobs/run', headers=headers, json={
        'config_path': 'config/example_config.yaml',
        'mode': 'dry_run',
        'tables': [],
        'verbose': False,
    })
    assert r.status_code == 200
    job_id = r.get_json()['job_id']

    r = client.get('/api/queue/stats', headers=headers)
    assert r.status_code == 200
    assert r.get_json()['queued'] >= 1

    assert run_once('pytest-worker') is True

    r = client.get(f'/api/jobs/{job_id}', headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body['status'] in ('completed', 'failed')
    assert body['worker_name'] == 'pytest-worker'


def test_audit_chain_verify_endpoint():
    token = admin_token()
    headers = {'Authorization': f'Bearer {token}'}
    r = client.get('/api/audit/verify', headers=headers)
    assert r.status_code == 200
    assert 'issues' in r.get_json()


def test_create_security_officer_role():
    token = admin_token()
    headers = {'Authorization': f'Bearer {token}'}
    uname = 'sec_' + uuid.uuid4().hex[:8]
    r = client.post('/api/users', headers=headers, json={'username': uname, 'password': 'StrongPass123!', 'role': 'security_officer', 'is_active': True})
    assert r.status_code == 200
