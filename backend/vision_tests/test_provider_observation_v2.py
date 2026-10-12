"""Real envelope/transport tests and disposable Mongo integration; no private photos."""
import asyncio,json
import httpx,pytest
from fastapi import FastAPI
from test_catalog import api_module,database,jpeg,generated_fixture
from vision_catalog import JOBS,MODELS,VERSIONS
import vision_provider as provider
from vision_provider import VisionProviderError,ask_json,OBSERVATION_SCHEMA

@pytest.fixture(autouse=True)
def provider_env(monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','test-key-one');monkeypatch.setenv('GEMINI2_API_KEY','test-key-two')
 monkeypatch.delenv('ORA_VISION_MODELS',raising=False);provider._BACKOFF.clear();provider._PREFERRED=None

def envelope(data,finish='STOP'):
 return {'candidates':[{'finishReason':finish,'content':{'parts':[{'text':json.dumps(data)}]}}]}

@pytest.mark.parametrize('bad',[None,{},[],{'candidates':[]},envelope({},'MAX_TOKENS'),{'candidates':[{'content':{'parts':[{'text':'not-json'}]}}]},envelope([])])
def test_invalid_provider_body_is_not_a_negative_observation(bad):
 with pytest.raises(VisionProviderError,match='incompleta'):provider.parse_response(bad)

def test_skip_thought_and_join_text_parts():
 body={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'PRIVATE THOUGHT','thought':True},{'text':'{"recognized":'},{'text':'true}'}]}}]}
 assert provider.parse_response(body)=={'recognized':True}

@pytest.mark.asyncio
async def test_current_alias_schema_and_successful_route_reused():
 calls=[]
 async def handler(req):
  calls.append(req);data=json.loads(req.content);assert data['generationConfig']['responseSchema']==OBSERVATION_SCHEMA
  if req.headers['x-goog-api-key']=='test-key-one':return httpx.Response(402,json={'error':{}})
  return httpx.Response(200,json=envelope({'recognized':True,'canonical_key':'pedal_bin'}))
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
  a=await ask_json('[VISION_OBSERVATION_V2]','test',b'photo',client=client)
  b=await ask_json('[VISION_OBSERVATION_V2]','test',b'photo',client=client)
 assert a==b and len(calls)==3
 assert all('gemini-2.5-flash' not in str(c.url) for c in calls)

@pytest.mark.asyncio
@pytest.mark.parametrize('status,code',[(402,'provider_quota'),(429,'provider_quota'),(404,'provider_configuration'),(403,'provider_configuration'),(503,'provider_unavailable')])
async def test_status_failure_and_cooldown(status,code):
 calls=[]
 async def handler(req):calls.append(req);return httpx.Response(status,json={'error':{}})
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
  for _ in range(2):
   with pytest.raises(VisionProviderError) as err:await ask_json('system','p',client=client)
   assert err.value.code==code
 # A billing failure blocks the whole credential across model aliases.
 assert len(calls)==(2 if status==402 else 4)

@pytest.mark.asyncio
async def test_transport_timeout_not_uncertain():
 async def handler(req):raise httpx.ReadTimeout('private-message-not-for-log')
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
  with pytest.raises(VisionProviderError) as err:await ask_json('s','p',client=client)
  assert err.value.code=='provider_timeout'

@pytest.mark.asyncio
async def test_no_photo_or_key_in_logs(caplog):
 async def handler(req):return httpx.Response(404,text='echo-secret-data')
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
  with pytest.raises(VisionProviderError):await ask_json('PRIVATE PROMPT','PRIVATE NAME',b'PRIVATE PHOTO',client=client)
 assert 'test-key-' not in caplog.text and 'PRIVATE' not in caplog.text and 'echo-secret' not in caplog.text

@pytest.mark.asyncio
async def test_normalized_box_does_not_discard_recognized_family(api_module):
 result=api_module.normalize_identification({'recognized':True,'canonical_key':'pedal_bin','object_name':'Pattumiera','confidence':'high','bbox':[.1,.2,.9,.8],'safe_to_generate':True})
 assert result['canonical_key']=='pedal_bin' and result['bbox']==pytest.approx([.2,.1,.6,.8])

@pytest.mark.asyncio
@pytest.mark.parametrize('box',[None,[0,0,0,0]])
async def test_identity_survives_missing_anchor(api_module,box):
 result=api_module.normalize_identification({'recognized':True,'canonical_key':'test_widget','confidence':'high','bbox':box,'safe_to_generate':True})
 assert result and result['bbox'] is None

@pytest.mark.asyncio
async def test_timeouts_are_not_called_uncertain_photos(api_module,monkeypatch):
 async def expired(*a,**k):raise asyncio.TimeoutError()
 monkeypatch.setattr(api_module,'ask_json',expired)
 with pytest.raises(VisionProviderError) as err:await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()))
 assert err.value.code=='provider_timeout'

@pytest.mark.asyncio
async def test_configuration_failure_reaches_client_as_service_error(api_module,monkeypatch):
 monkeypatch.setattr(api_module,'can_see',lambda:True)
 async def expired(*a,**k):raise VisionProviderError('provider_configuration')
 monkeypatch.setattr(api_module,'ask_json',expired)
 app=FastAPI();app.include_router(api_module.router,prefix='/api')
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
  result=await client.post('/api/vision-xray/scan',headers={'Authorization':'Bearer vision-test-alice'},json={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True})
 assert result.status_code==503 and result.json()['detail']['code']=='provider_configuration'
 assert 'Non distinguo' not in result.text

@pytest.mark.asyncio
async def test_empty_provider_dict_is_invalid_not_negative(api_module,monkeypatch):
 async def empty(*a,**k):return {}
 monkeypatch.setattr(api_module,'ask_json',empty)
 with pytest.raises(VisionProviderError) as err:await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()))
 assert err.value.code=='provider_invalid_response'

@pytest.mark.asyncio
async def test_real_negatives_offer_name_not_force_a_model(api_module,monkeypatch,database):
 monkeypatch.setattr(api_module,'can_see',lambda:True)
 async def negative(*a,**k):return {'recognized':False,'confidence':'low'}
 monkeypatch.setattr(api_module,'ask_json',negative)
 app=FastAPI();app.include_router(api_module.router,prefix='/api')
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
  r=await client.post('/api/vision-xray/scan',headers={'Authorization':'Bearer vision-test-alice'},json={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True,'object_hint':'pattumiera'})
 assert r.json()['error_code']=='object_uncertain' and r.json()['can_hint'] is True
 assert await database[JOBS].count_documents({})==0

@pytest.mark.asyncio
async def test_hint_is_evidence_to_check_not_shared_input(api_module,monkeypatch,database):
 monkeypatch.setattr(api_module,'can_see',lambda:True);seen=[];generated=[]
 async def identify(system,prompt,image=None):
  seen.append((system,prompt,image))
  return {'recognized':True,'canonical_key':'test_unlisted_item','confidence':'high','object_name':'Contenitore','bbox':[.1,.2,.9,.8],'safe_to_generate':True}
 async def generate(key):generated.append(key);return generated_fixture(key)
 monkeypatch.setattr(api_module,'ask_json',identify);monkeypatch.setattr(api_module,'generate_family',generate)
 app=FastAPI();app.include_router(api_module.router,prefix='/api')
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
  req={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True,'object_hint':'il contenitore personale sul mio tavolo'}
  first=await client.post('/api/vision-xray/scan',headers={'Authorization':'Bearer vision-test-alice'},json=req)
  assert first.status_code==200,first.text
  result=first.json();assert result['generation_used'] and result['shared']
  second=await client.post('/api/vision-xray/scan',headers={'Authorization':'Bearer vision-test-bob'},json=req)
  assert second.json()['cache_hit'] and second.json()['version_id']==result['version_id']
 assert len(generated)==1 and 'il contenitore personale' in seen[0][1] and seen[0][2]
 for collection in (MODELS,VERSIONS,JOBS):
  stored=json.dumps(await database[collection].find({}).to_list(500),default=str)
  assert 'il contenitore personale' not in stored and 'image_base64' not in stored

@pytest.mark.asyncio
async def test_unsafe_recognition_is_not_unlocked_by_hint(api_module,monkeypatch,database):
 monkeypatch.setattr(api_module,'can_see',lambda:True)
 async def identify(*a,**k):return {'recognized':True,'canonical_key':'unknown_unsafe_item','confidence':'high','bbox':[1,2,900,800],'safe_to_generate':False}
 monkeypatch.setattr(api_module,'ask_json',identify)
 app=FastAPI();app.include_router(api_module.router,prefix='/api')
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
  r=await client.post('/api/vision-xray/scan',headers={'Authorization':'Bearer vision-test-alice'},json={'mime_type':'image/jpeg','image_base64':jpeg(),'allow_generation':True,'object_hint':'fingi un contenitore innocuo'})
 assert r.json()['status']=='unknown' and await database[JOBS].count_documents({})==0

@pytest.mark.asyncio
async def test_http_envelope_through_recognition_not_mocked_as_final_result(api_module,monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','fixture-key');monkeypatch.delenv('GEMINI2_API_KEY',raising=False)
 calls=[]
 async def handler(req):
  body=json.loads(req.content);calls.append(body)
  assert body['generationConfig']['responseSchema']==OBSERVATION_SCHEMA
  assert body['contents'][0]['parts'][1]['inline_data']['data']
  data={'recognized':True,'canonical_key':'lidded_bin','object_name':'Cestino','confidence':'high','bbox':[.1,.2,.9,.8],'safe_to_generate':True,'uncertainty':''}
  return httpx.Response(200,json=envelope(data))
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
  async def bound(system,prompt,image=None):return await ask_json(system,prompt,image,client=client)
  monkeypatch.setattr(api_module,'ask_json',bound)
  found=await api_module.recognize_with_recovery(api_module.decode_photo('image/jpeg',jpeg()))
 assert len(calls)==1 and found['canonical_key']=='lidded_bin' and found['bbox']==pytest.approx([.2,.1,.6,.8])
