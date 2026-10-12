"""One-shot smoke on the user's deployed ORA, with isolated QA accounts.

Uses a public CC BY-SA photograph by Rodw, NOT the private uploaded screenshot.
No keys/passwords/photos in artifacts. No mock AI or auth. Three bounded scans
plus optional single hinted retry; no new seed used to make the test pass.
"""
import base64, hashlib, io, json, secrets, time, uuid
from pathlib import Path
from urllib.parse import quote, urlencode
import httpx
from PIL import Image, ImageOps

API='https://ora-backend-production-aa56.up.railway.app'
OUT=Path('.vision-provider-live');OUT.mkdir(exist_ok=True)
REPORT={'physical_iphone_tested':False,'user_photo_tested':False,'ai_mocked':False,'checks':[],
 'source':{'author':'Rodw','license':'CC BY-SA 4.0','page':'https://commons.wikimedia.org/wiki/File:Beldray_pedal_bin.jpg'}}
def record(name,**fields):
 row={'check':name,**fields};REPORT['checks'].append(row)
 (OUT/'report.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False));print(json.dumps(row,ensure_ascii=False),flush=True)
def load_photo(c):
 name='Beldray_pedal_bin.jpg';h=hashlib.md5(name.encode()).hexdigest()
 origin=f'https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{name}'
 urls=[origin,'https://wsrv.nl/?'+urlencode({'url':origin,'w':960,'output':'jpg'}),'https://images.weserv.nl/?'+urlencode({'url':origin,'w':960,'output':'jpg'})]
 for url in urls:
  try:
   r=c.get(url,follow_redirects=True,timeout=25)
   if r.status_code!=200:continue
   with Image.open(io.BytesIO(r.content)) as source:
    frame=ImageOps.exif_transpose(source).convert('RGB');frame.thumbnail((960,960));out=io.BytesIO();frame.save(out,'JPEG',quality=80)
   record('public_photo_loaded',width=frame.width,height=frame.height)
   return base64.b64encode(out.getvalue()).decode()
  except (httpx.HTTPError,OSError):continue
 raise RuntimeError('Public photo unavailable; no account created')
def register(c):
 credentials={'email':'ora-vision-qa-'+uuid.uuid4().hex+'@example.com','password':secrets.token_urlsafe(32),'first_name':'Collaudo','last_name':'Vision','tutorial_seen':True}
 r=c.post(API+'/api/auth/register',json=credentials);r.raise_for_status();return r.json()['token']
def scan(c,token,photo,name,generate=False,hint=''):
 start=time.monotonic()
 r=c.post(API+'/api/vision-xray/scan',headers={'Authorization':'Bearer '+token},json={'mime_type':'image/jpeg','image_base64':photo,'frame_id':'qa-'+name,'allow_generation':generate,'object_hint':hint})
 data=r.json()
 detail=data.get('detail',{})
 record(name,http_status=r.status_code,seconds=round(time.monotonic()-start,2),status=data.get('status'),
  code=data.get('code') or (detail.get('code') if isinstance(detail,dict) else None),
  reason=data.get('reason') or (detail.get('message') if isinstance(detail,dict) else detail),
  identity=data.get('identification',{}).get('canonical_key'),method=data.get('identification',{}).get('recognition_method'),
  cache_hit=data.get('cache_hit'),generation_used=data.get('generation_used'),version_id=data.get('version_id'),
  parts=len(data.get('manifest',{}).get('parts',[])))
 return r.status_code,data

def main():
 with httpx.Client(timeout=85,headers={'User-Agent':'ORA-Vision-QA/1.0'}) as c:
  photo=load_photo(c)
  token=register(c);headers={'Authorization':'Bearer '+token}
  # Baseline is read-only for catalogue generation. Old API doesn't accept the hint field.
  start=time.monotonic()
  baseline=c.post(API+'/api/vision-xray/scan',headers=headers,json={'mime_type':'image/jpeg','image_base64':photo,'allow_generation':False})
  data=baseline.json();record('baseline_before_pipeline_update',http_status=baseline.status_code,seconds=round(time.monotonic()-start,2),status=data.get('status'),reason=data.get('reason'),identified=data.get('identification',{}).get('canonical_key'))
  for _ in range(120):
   response=c.get(API+'/api/vision-xray/available',headers=headers)
   if response.status_code==200 and response.json().get('recognition_pipeline')=='provider-health-v2':break
   time.sleep(10)
  else:raise RuntimeError('New pipeline not deployed during this bounded check')
  record('new_pipeline_available',value='provider-health-v2')
  status,first=scan(c,token,photo,'new_pipeline_missing_family',True)
  if status!=200 or first.get('status')!='family':
   time.sleep(15)
   status,first=scan(c,token,photo,'new_pipeline_hinted_retry',True,'un cestino con pedale')
  if status!=200 or first.get('status')!='family':raise RuntimeError('Public bin did not reach a usable model; do not report real-provider success')
  key=first['manifest']['canonical_key']
  if not any(term in key for term in ('bin','trash','waste','rubbish')):raise RuntimeError('Returned family does not describe the public test bin')
  if first.get('source_type')=='seed':raise RuntimeError('Test hit a seed; outside-catalog generation not proved')
  # Save only the generalized model for inspection, never the photograph.
  (OUT/'generic-bin-model.json').write_text(json.dumps(first['manifest'],ensure_ascii=False,indent=2))
  other=register(c)
  status,second=scan(c,other,photo,'second_account_reuses',True)
  if status!=200 or not second.get('cache_hit') or second.get('generation_used') or first['version_id']!=second.get('version_id'):
   raise RuntimeError('Same generated family was not reused across accounts')
  record('complete',same_version=True,shared=first.get('shared'),first_generation=first.get('generation_used'))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  record('failed',error_type=type(exc).__name__,message=str(exc)[:160]);raise SystemExit(1)
