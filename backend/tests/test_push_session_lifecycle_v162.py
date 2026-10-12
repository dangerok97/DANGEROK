"""Session-bound native endpoints; isolated Mongo and intercepted provider only."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from mongomock_motor import AsyncMongoMockClient
from ambient.push import ExpoNotificationProvider, PushEndpointService
from ambient.repository import AmbientRepository
from session_revocation import revoke, token_digest

A, B = 'synthetic-owner-a', 'synthetic-owner-b'
DEVICE, PUSH = 'synthetic-shared-installation', 'ExponentPushToken[synthetic-session-lifecycle]'


def expiry(delta=1):
    return (datetime.now(timezone.utc) + timedelta(days=delta)).isoformat()


async def bound(db, owner=A, credential='synthetic-session-a', device=DEVICE, push=PUSH):
    return await PushEndpointService(db).register(owner, token=push, device=device, platform='ios',
        session_digest=token_digest(credential), session_expires_at=expiry(), device_revision=20 if owner == B else 10)


async def invalidate(db, credential='synthetic-session-a'):
    await revoke(db, credential, (datetime.now(timezone.utc) + timedelta(days=1)).timestamp())


@pytest.mark.asyncio
async def test_session_metadata_is_server_only_and_registration_is_idempotent():
    db = AsyncMongoMockClient().push_session_binding
    first, second = await bound(db), await bound(db)
    assert first['endpoint']['id'] == second['endpoint']['id']
    assert await db.push_endpoints.count_documents({}) == 1
    stored = await db.push_endpoints.find_one({})
    assert stored['session_digest'] == token_digest('synthetic-session-a')
    assert stored['session_expires_at']
    for private in ('token', 'session_digest', 'session_expires_at'):
        assert private not in second['endpoint']


@pytest.mark.asyncio
async def test_legacy_endpoint_stays_reachable_then_migrates_on_registration():
    db = AsyncMongoMockClient().push_legacy_migration
    legacy = await PushEndpointService(db).register(A, token=PUSH, device=DEVICE)
    assert len(await AmbientRepository(db).active_endpoints(A)) == 1
    migrated = await bound(db)
    assert migrated['endpoint']['id'] == legacy['endpoint']['id']
    await invalidate(db)
    assert await AmbientRepository(db).active_endpoints(A) == []


@pytest.mark.asyncio
async def test_expired_or_revoked_session_cannot_reach_provider(monkeypatch):
    db = AsyncMongoMockClient().push_expired_delivery
    await bound(db)
    await db.push_endpoints.update_one({}, {'$set': {'session_expires_at': expiry(-1)}})
    provider = ExpoNotificationProvider(db); post = AsyncMock()
    monkeypatch.setattr(provider, '_post', post)
    result = await provider.send(owner_id=A, plan_id='dlv_synthetic_session', title='synthetic', body='synthetic', deep_link='/')
    assert result['reason'] == 'no_endpoint'; post.assert_not_awaited()
    await bound(db); await invalidate(db)
    assert await AmbientRepository(db).active_endpoints(A) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('digest,expires', [('missing-expiry', None), ('', 'bad-time'), ('digest', '2026-01-01T10:00:00')])
async def test_partial_or_invalid_session_binding_fails_closed(digest, expires):
    db = AsyncMongoMockClient().push_bad_binding
    await db.push_endpoints.insert_one({'id': 'pep_synthetic_partial', 'owner_id': A, 'token': PUSH,
        'device_hash': 'synthetic', 'status': 'active', 'session_digest': digest, 'session_expires_at': expires})
    assert await AmbientRepository(db).active_endpoints(A) == []


@pytest.mark.asyncio
async def test_revoked_session_registration_does_not_release_the_new_owner():
    db = AsyncMongoMockClient().push_rejected_registration
    await bound(db, owner=B, credential='synthetic-session-b'); await invalidate(db)
    assert (await bound(db))['reason'] == 'session_inactive'
    assert len(await AmbientRepository(db).active_endpoints(B)) == 1


@pytest.mark.asyncio
async def test_late_old_session_release_cannot_revoke_new_login_even_for_same_owner():
    db = AsyncMongoMockClient().push_scoped_release
    await bound(db); await bound(db, credential='synthetic-new-session-a')
    result = await PushEndpointService(db).release_device(A, DEVICE, session_digest=token_digest('synthetic-session-a'))
    assert result['released'] == 0
    assert len(await AmbientRepository(db).active_endpoints(A)) == 1
    await bound(db, owner=B, credential='synthetic-session-b')
    assert (await PushEndpointService(db).release_device(A, DEVICE, session_digest=token_digest('synthetic-new-session-a')))['released'] == 0
    assert len(await AmbientRepository(db).active_endpoints(B)) == 1


@pytest.mark.asyncio
async def test_logout_finishing_during_registration_never_restores_old_session(monkeypatch):
    db = AsyncMongoMockClient().push_logout_race
    service = PushEndpointService(db); original = service.repo.upsert_endpoint
    async def write_then_logout(endpoint):
        result = await original(endpoint)
        await invalidate(db)
        await bound(db, owner=B, credential='synthetic-session-b')
        return result
    monkeypatch.setattr(service.repo, 'upsert_endpoint', write_then_logout)
    result = await service.register(A, token=PUSH, device=DEVICE, session_digest=token_digest('synthetic-session-a'), session_expires_at=expiry(), device_revision=10)
    assert result['reason'] == 'session_inactive'
    assert await service.repo.active_endpoints(A) == []
    assert len(await service.repo.active_endpoints(B)) == 1


@pytest.mark.asyncio
async def test_registration_paused_before_device_release_cannot_clobber_new_owner(monkeypatch):
    db = AsyncMongoMockClient().push_before_release_race
    service = PushEndpointService(db); original = service.repo.revoke_device
    async def logout_and_switch_before_release(**kwargs):
        await invalidate(db)
        await bound(db, owner=B, credential='synthetic-session-b')
        return await original(**kwargs)
    monkeypatch.setattr(service.repo, 'revoke_device', logout_and_switch_before_release)
    result = await service.register(A, token=PUSH, device=DEVICE,
        session_digest=token_digest('synthetic-session-a'), session_expires_at=expiry(), device_revision=10)
    assert result['ok'] is False
    assert len(await service.repo.active_endpoints(B)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('old_token', [PUSH, 'ExponentPushToken[synthetic-old-rotated]'])
async def test_delayed_old_request_cannot_win_even_before_its_logout_reaches_server(old_token):
    db = AsyncMongoMockClient().push_delayed_old_request
    await bound(db, owner=B, credential='synthetic-session-b')
    result = await bound(db, push=old_token)
    assert result['reason'] == 'superseded_registration'
    assert await AmbientRepository(db).active_endpoints(A) == []
    assert len(await AmbientRepository(db).active_endpoints(B)) == 1


@pytest_asyncio.fixture
async def api_setup(monkeypatch):
    import deps
    from ambient import router as push_router
    from routers import auth as auth_router
    db = AsyncMongoMockClient().push_session_http
    monkeypatch.setattr(deps, 'db', db); monkeypatch.setattr(auth_router, 'db', db)
    for owner in (A, B):
        await db.users.insert_one({'user_id': owner, 'provider': 'password', 'email': f'{owner}@example.invalid'})
    tokens = {owner: deps.make_jwt(owner) for owner in (A, B)}
    app = FastAPI(); app.include_router(push_router.router, prefix='/api'); app.include_router(auth_router.router, prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic.invalid') as client:
        yield db, client, tokens, app


@pytest.mark.asyncio
async def test_http_registration_ignores_client_session_fields_and_logout_revokes_only_its_session(api_setup):
    db, client, tokens, _ = api_setup
    response = await client.post('/api/ambient/push/register', headers={'Authorization': f'Bearer {tokens[A]}'},
        json={'token': PUSH, 'device': DEVICE, 'platform': 'ios', 'session_digest': 'forged-session', 'session_expires_at': '2099-01-01T00:00:00Z'})
    assert response.status_code == 200
    stored = await db.push_endpoints.find_one({'token': PUSH})
    assert stored['session_digest'] == token_digest(tokens[A])
    assert not stored['session_expires_at'].startswith('2099')
    await bound(db, owner=B, credential=tokens[B], device='other-device', push='ExponentPushToken[other-synthetic-device]')
    response = await client.post('/api/auth/logout', headers={'Authorization': f'Bearer {tokens[A]}'})
    assert response.status_code == 200
    assert (await db.push_endpoints.find_one({'token': PUSH}))['status'] == 'revoked'
    assert await AmbientRepository(db).active_endpoints(A) == []
    assert len(await AmbientRepository(db).active_endpoints(B)) == 1
    response = await client.post('/api/ambient/push/register', headers={'Authorization': f'Bearer {tokens[A]}'}, json={'token': PUSH, 'device': DEVICE})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_http_403_never_mutates_another_accounts_endpoints(api_setup):
    import deps
    db, client, _, app = api_setup
    await bound(db, owner=B, credential='synthetic-b-session')
    async def forbidden():
        raise HTTPException(status_code=403, detail='synthetic forbidden')
    app.dependency_overrides[deps.get_current_user] = forbidden
    before = await db.push_endpoints.find_one({})
    for path in ('/api/ambient/push/register', '/api/ambient/push/release', '/api/auth/logout'):
        response = await client.post(path, headers={'Authorization': 'Bearer synthetic-rejected'}, json={'token': PUSH, 'device': DEVICE})
        assert response.status_code == 403
    assert await db.push_endpoints.find_one({}) == before


@pytest.mark.asyncio
async def test_explicit_enable_also_records_the_real_delivery_consent(api_setup):
    from life_attention.context import notifications_allowed
    db, client, tokens, _ = api_setup
    assert not await notifications_allowed(db, A)
    response = await client.post('/api/ambient/push/register', headers={'Authorization': f'Bearer {tokens[A]}'},
        json={'token': PUSH, 'device': DEVICE, 'platform': 'ios', 'device_revision': 1,
              'permission_state': 'granted', 'request_delivery_permission': True})
    assert response.status_code == 200
    assert response.json()['delivery_allowed'] is True
    assert await notifications_allowed(db, A)


@pytest.mark.asyncio
async def test_foreground_registration_never_grants_or_restores_account_consent(api_setup):
    from life_attention.context import notifications_allowed
    from permissions.service import PermissionService
    db, client, tokens, _ = api_setup
    headers = {'Authorization': f'Bearer {tokens[A]}'}
    body = {'token': PUSH, 'device': DEVICE, 'platform': 'ios', 'permission_state': 'granted'}
    first = await client.post('/api/ambient/push/register', headers=headers, json=body)
    assert first.status_code == 200
    assert first.json()['delivery_available'] is True
    assert first.json()['delivery_allowed'] is False
    assert not await notifications_allowed(db, A)
    permissions = PermissionService(db)
    await permissions.grant(user_id=A, capability_id='notifications.deliver', connector_id='notifications')
    await permissions.revoke(user_id=A, capability_id='notifications.deliver', connector_id='notifications')
    second = await client.post('/api/ambient/push/register', headers=headers, json=body)
    assert second.status_code == 200
    assert second.json()['delivery_allowed'] is False
    assert not await notifications_allowed(db, A)


@pytest.mark.asyncio
async def test_disabled_delivery_is_reported_without_invalidating_the_session(api_setup):
    from permissions.service import PermissionService
    db, client, tokens, _ = api_setup
    permissions = PermissionService(db)
    await permissions.sync_registry()
    await permissions.set_enabled('notifications.deliver', False)
    response = await client.post('/api/ambient/push/register', headers={'Authorization': f'Bearer {tokens[A]}'},
        json={'token': PUSH, 'device': DEVICE, 'platform': 'ios',
              'permission_state': 'granted', 'request_delivery_permission': True})
    assert response.status_code == 200
    assert response.json()['delivery_allowed'] is False
    assert response.json()['delivery_available'] is False
    assert len(await AmbientRepository(db).active_endpoints(A)) == 1


@pytest.mark.asyncio
async def test_logout_retires_legacy_endpoints_without_revoking_another_bound_session(api_setup):
    db, client, tokens, _ = api_setup
    service = PushEndpointService(db)
    await service.register(A, token=PUSH, device=DEVICE)
    await bound(db, credential='synthetic-other-session-a', device='other-a-device',
                push='ExponentPushToken[synthetic-other-a]')
    await service.register(B, token='ExponentPushToken[synthetic-legacy-b]', device='other-b-device')
    response = await client.post('/api/auth/logout', headers={'Authorization': f'Bearer {tokens[A]}'})
    assert response.status_code == 200
    assert (await db.push_endpoints.find_one({'token': PUSH}))['status'] == 'revoked'
    assert len(await AmbientRepository(db).active_endpoints(A)) == 1
    assert len(await AmbientRepository(db).active_endpoints(B)) == 1
