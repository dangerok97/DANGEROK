"""Reproduce observed provider failures without keys, personal photos or billing.
The transport is mocked; Mongo lifecycle fixtures remain real disposable Mongo.
"""
import asyncio
import json
import httpx
import pytest
from fastapi import FastAPI
import vision_provider as provider
from test_catalog import api_module, database, jpeg, generated_fixture

@pytest.fixture
def transport_setup(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-denied-key')
    monkeypatch.setenv('GEMINI2_API_KEY','synthetic-working-key')
    monkeypatch.setenv('ORA_VISION_MODELS','missing-model,working-model')
    monkeypatch.setattr(provider,'_health',provider.RouteHealth())
    original=httpx.AsyncClient
    def install(handler):
        transport=httpx.MockTransport(handler)
        monkeypatch.setattr(provider.httpx,'AsyncClient',lambda **kwargs:original(transport=transport,**kwargs))
    return install

def response(value,finish='STOP'):
    return {'candidates':[{'finishReason':finish,'content':{'parts':[{'text':json.dumps(value)}]}}]}

def identification(key='lidded_waste_bin'):
    return {'recognized':True,'canonical_key':key,'object_name':'Contenitore con coperchio',
            'confidence':'high','bbox':[100,200,900,800],'safe_to_generate':True,'uncertainty':''}

@pytest.mark.asyncio
async def test_observed_404_402_routes_are_not_retried_on_every_scan(transport_setup):
    calls=[]
    async def handler(request):
        calls.append((request.url.path,request.headers['x-goog-api-key']))
        if 'missing-model' in request.url.path:return httpx.Response(404)
        if request.headers['x-goog-api-key']=='synthetic-denied-key':return httpx.Response(402)
        return httpx.Response(200,json=response(identification()))
    transport_setup(handler)
    assert (await provider.ask_json('system','prompt',b'fixture'))['recognized']
    assert len(calls)==4
    assert (await provider.ask_json('system','prompt',b'fixture'))['recognized']
    assert len(calls)==5 and 'working-model' in calls[-1][0]
    assert calls[-1][1]=='synthetic-working-key'
    assert 'synthetic-working-key' not in repr(provider._health.__dict__)

@pytest.mark.asyncio
async def test_image_request_has_typed_detection_contract(transport_setup):
    requests=[]
    async def handler(request):
        requests.append(json.loads(request.content));return httpx.Response(200,json=response(identification()))
    transport_setup(handler)
    await provider.ask_json('system','prompt',b'fixture')
    await provider.ask_json('system','generate')
    assert requests[0]['generationConfig']['responseSchema']['properties']['recognized']['type']=='BOOLEAN'
    assert 'responseSchema' not in requests[1]['generationConfig']

@pytest.mark.asyncio
@pytest.mark.parametrize('status,code',[(402,'provider_billing'),(404,'provider_access'),(429,'provider_busy'),(503,'provider_unavailable')])
async def test_http_error_is_not_a_negative_identification(transport_setup,status,code):
    transport_setup(lambda req:httpx.Response(status))
    with pytest.raises(provider.VisionProviderError) as caught:await provider.ask_json('system','prompt',b'fixture')
    assert caught.value.code==code
    assert 'Non distinguo' not in str(caught.value)

@pytest.mark.asyncio
async def test_transport_timeout_stays_a_timeout(transport_setup):
    async def timed_out(request):raise httpx.ReadTimeout('synthetic')
    transport_setup(timed_out)
    with pytest.raises(provider.VisionProviderError) as caught:await provider.ask_json('system','prompt',b'fixture')
    assert caught.value.code=='provider_timeout'

@pytest.mark.parametrize('data',[{}, {'candidates':[]},response({},'MAX_TOKENS'),response([], 'STOP'),{'candidates':[{'content':{'parts':[{'text':'{truncated'}]}}]}])
def test_incomplete_provider_reply_is_not_an_unrecognized_object(data):
    with pytest.raises(provider.VisionProviderError):provider.parse_response(data)

def test_successful_explicit_negative_response_is_preserved():
    value={'recognized':False,'confidence':'low'}
    assert provider.parse_response(response(value))==value

@pytest.mark.asyncio
async def test_old_timeout_collapse_is_reproduced_and_fixed(api_module,monkeypatch):
    calls=[]
    async def timeout(*args,**kwargs):calls.append(1);raise asyncio.TimeoutError()
    monkeypatch.setattr(api_module,'ask_json',timeout)
    with pytest.raises(provider.VisionProviderError) as error:
        await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()))
    assert len(calls)==2 and error.value.code=='provider_timeout'

@pytest.mark.asyncio
async def test_cropped_timeout_after_primary_negative_is_not_declared_unseen(api_module,monkeypatch):
    calls=[]
    async def answer(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:return {'recognized':False,'confidence':'low'}
        raise asyncio.TimeoutError()
    monkeypatch.setattr(api_module,'ask_json',answer)
    with pytest.raises(provider.VisionProviderError):
        await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()))

@pytest.mark.asyncio
async def test_normalized_box_does_not_discard_correct_identity(api_module):
    raw=identification();raw['bbox']=[.1,.2,.9,.8]
    found=api_module.normalize_identification(raw)
    assert found['bbox']==pytest.approx([.2,.1,.6,.8])
    raw['bbox']=[-.1,.2,.9,.8]
    assert api_module.normalize_identification(raw) is None

@pytest.mark.asyncio
async def test_open_recognition_does_not_require_membership_in_catalog(api_module,monkeypatch):
    prompts=[]
    async def answer(system,prompt,image=None):prompts.append((system,prompt));return identification()
    monkeypatch.setattr(api_module,'ask_json',answer)
    out=await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()),'una pattumiera')
    assert out['canonical_key']=='lidded_waste_bin'
    assert 'spinning_reel' not in prompts[0][0]
    assert 'una pattumiera' in prompts[0][1]
    assert 'NON VERIFICATA' in prompts[0][0]

@pytest.mark.asyncio
async def test_hint_does_not_bypass_visual_refusal(api_module,monkeypatch):
    async def negative(*args,**kwargs):return {'recognized':False,'confidence':'low'}
    monkeypatch.setattr(api_module,'ask_json',negative)
    assert await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()),'telecomando') is None

@pytest.mark.asyncio
async def test_api_timeout_and_uncertain_have_different_outcomes(api_module,monkeypatch):
    monkeypatch.setattr(api_module,'can_see',lambda:True)
    app=FastAPI();app.include_router(api_module.router,prefix='/api')
    headers={'Authorization':'Bearer vision-test-alice'}
    body={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        async def timeout(*args,**kwargs):raise provider.VisionProviderError('provider_timeout')
        monkeypatch.setattr(api_module,'ask_json',timeout)
        failed=await client.post('/api/vision-xray/scan',json=body,headers=headers)
        assert failed.status_code==504
        assert failed.json()['detail']['code']=='provider_timeout'
        async def negative(*args,**kwargs):return {'recognized':False,'confidence':'low'}
        monkeypatch.setattr(api_module,'ask_json',negative)
        uncertain=await client.post('/api/vision-xray/scan',json=body,headers=headers)
        assert uncertain.status_code==200 and uncertain.json()['can_describe']
        assert uncertain.json()['code']=='recognition_uncertain'

@pytest.mark.asyncio
async def test_unknown_family_generates_then_another_account_reuses_it(api_module,monkeypatch,database):
    monkeypatch.setattr(api_module,'can_see',lambda:True)
    calls=[]
    async def detect(*args,**kwargs):return identification()
    async def generate(key):calls.append(key);return generated_fixture(key)
    monkeypatch.setattr(api_module,'ask_json',detect);monkeypatch.setattr(api_module,'generate_family',generate)
    app=FastAPI();app.include_router(api_module.router,prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        body={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True,'object_hint':'private hint not stored'}
        one=(await client.post('/api/vision-xray/scan',json=body,headers={'Authorization':'Bearer vision-test-alice'})).json()
        two=(await client.post('/api/vision-xray/scan',json=body,headers={'Authorization':'Bearer vision-test-bob'})).json()
        assert one['generation_used'] and not one['cache_hit'] and one['shared']
        assert two['cache_hit'] and not two['generation_used'] and one['version_id']==two['version_id']
    assert calls==['lidded_waste_bin']
    for collection in ('vision_catalog_models','vision_catalog_versions','vision_build_jobs'):
        assert 'private hint not stored' not in json.dumps(await database[collection].find({}).to_list(200),default=str)

@pytest.mark.asyncio
async def test_generation_provider_failure_does_not_publish_or_hide_the_cause(api_module,monkeypatch,database):
    monkeypatch.setattr(api_module,'can_see',lambda:True)
    async def detect(*args,**kwargs):return identification()
    async def failed(key):raise provider.VisionProviderError('provider_billing')
    monkeypatch.setattr(api_module,'ask_json',detect);monkeypatch.setattr(api_module,'generate_family',failed)
    app=FastAPI();app.include_router(api_module.router,prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        resp=await client.post('/api/vision-xray/scan',headers={'Authorization':'Bearer vision-test-alice'},json={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True})
        assert resp.status_code==503 and resp.json()['detail']['code']=='provider_billing'
    assert await database.vision_catalog_models.count_documents({'canonical_key':'lidded_waste_bin'})==0

@pytest.mark.parametrize('content',[None,[],42,{'parts':None},{'parts':'invalid'}])
def test_bad_content_envelope_returns_structured_error(content):
    with pytest.raises(provider.VisionProviderError):
        provider.parse_response({'candidates':[{'content':content}]})
