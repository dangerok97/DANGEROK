"""HTTP contract with synthetic auth/DB; real JWT validation stays in auth tests."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from test_loyalty_wallet import SECRET, card, service


@pytest.fixture
def http_wallet(monkeypatch):
    svc, db = service()
    dependency = ModuleType('deps')
    async def current_user(authorization: str | None = Header(None)):
        if authorization not in ('Bearer synthetic-alice', 'Bearer synthetic-bob'):
            raise HTTPException(401, 'Authentication required')
        return {'user_id': authorization.removeprefix('Bearer synthetic-')}
    dependency.db = db
    dependency.get_current_user = current_user
    monkeypatch.setitem(sys.modules, 'deps', dependency)
    monkeypatch.setenv('TOKEN_VAULT_KEY', SECRET)
    path = Path(__file__).resolve().parents[1] / 'backend/routers/loyalty_wallet.py'
    spec = importlib.util.spec_from_file_location('wallet_http_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_service', lambda: svc)
    app = FastAPI()
    app.include_router(module.router, prefix='/api')
    with TestClient(app) as client:
        yield client, module, db


@pytest.mark.parametrize('method,path', [('GET', '/cards'), ('PUT', '/cards'), ('DELETE', '/cards/'+'a'*32+'?revision=1'), ('POST', '/decode')])
def test_all_http_operations_require_authentication(http_wallet, method, path):
    client, _, _ = http_wallet
    assert client.request(method, '/api/wallet'+path, json=card().model_dump()).status_code == 401


def test_http_owner_scoping_no_store_and_revision_conflict(http_wallet):
    client, _, _ = http_wallet
    alice = {'Authorization': 'Bearer synthetic-alice'}
    bob = {'Authorization': 'Bearer synthetic-bob'}
    created = client.put('/api/wallet/cards', json=card().model_dump(), headers=alice)
    assert created.status_code == 200
    assert created.headers['cache-control'] == 'private, no-store'
    saved = created.json()['card']
    assert client.get('/api/wallet/cards', headers=bob).json()['cards'] == []
    assert client.delete('/api/wallet/cards/'+saved['id']+'?revision=1', headers=bob).status_code == 200
    assert len(client.get('/api/wallet/cards', headers=alice).json()['cards']) == 1
    changed = {**card().model_dump(), 'revision': 1, 'name': 'Changed'}
    assert client.put('/api/wallet/cards', json=changed, headers=alice).status_code == 200
    assert client.put('/api/wallet/cards', json=changed, headers=alice).status_code == 409
    assert client.delete('/api/wallet/cards/'+saved['id']+'?revision=2', headers=alice).status_code == 200
    assert client.get('/api/wallet/cards', headers=alice).json()['cards'] == []


def test_http_rejects_unsupported_uploads_and_never_saves_on_decode(http_wallet, monkeypatch):
    client, module, db = http_wallet
    headers = {'Authorization': 'Bearer synthetic-alice', 'Content-Type': 'image/svg+xml'}
    assert client.post('/api/wallet/decode', content=b'<svg/>', headers=headers).status_code == 415
    headers['Content-Type'] = 'image/png'
    assert client.post('/api/wallet/decode', content=b'x'*(8*1024*1024+1), headers=headers).status_code == 413
    monkeypatch.setattr(module, 'decode_image', lambda _: [{'format':'CODE_128', 'code':'00012345'}])
    decoded = client.post('/api/wallet/decode', content=b'synthetic-photo', headers=headers)
    assert decoded.status_code == 200 and decoded.json()['saved'] is False
    assert db.loyalty_wallets.docs == {}


def test_http_requires_static_confirmation(http_wallet):
    client, _, _ = http_wallet
    response = client.put('/api/wallet/cards', headers={'Authorization':'Bearer synthetic-alice'}, json={**card().model_dump(), 'static_confirmed':False})
    assert response.status_code == 422
