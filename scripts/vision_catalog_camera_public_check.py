"""Bounded public read: no credentials, personal data, registration or writes.
This verifies served assets and HTTP boundaries, NOT a physical torch or an
AI-authenticated scan. The real database/catalogue has separate isolated CI tests.
"""
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

WEB = 'https://ora-web-production-fb67.up.railway.app'
API = 'https://ora-backend-production-aa56.up.railway.app'
OUT = Path('.vision-catalog-camera-public'); OUT.mkdir(exist_ok=True)
MARKERS = ['vision-torch','vision-camera-zoom-toggle','vision-camera-zoom-range',
           'vision-catalog-search','vision-catalog-category']

def read(url):
    req = urllib.request.Request(url, headers={'User-Agent':'ORA-Public-Asset-QA/1.0', 'Cache-Control':'no-cache'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data=response.read(20*1024*1024+1)
            if len(data)>20*1024*1024: raise ValueError('Read budget exceeded')
            return response.status, data.decode('utf-8')
    except urllib.error.HTTPError as error:
        return error.code, ''

cache = {}
for attempt in range(24):
    try:
        status, html = read(WEB+'/vision-xray')
        paths = re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',html)
        found=set(); assets=[]
        for path in paths[:6]:
            url=urllib.parse.urljoin(WEB,path)
            if urllib.parse.urlparse(url).netloc != urllib.parse.urlparse(WEB).netloc: continue
            if url not in cache:
                code,data=read(url)
                if code != 200: continue
                cache[url]=[marker for marker in MARKERS if marker in data]
            found.update(cache[url]); assets.append(url)
        if status==200 and set(MARKERS)<=found:
            web_health,_=read(WEB+'/healthz')
            backend_health,_=read(API+'/api/health')
            protected_catalog,_=read(API+'/api/vision-xray/catalog')
            report=dict(public_assets_verified=True, markers=MARKERS, assets=assets,
                        web_health_status=web_health, backend_health_status=backend_health,
                        unauthenticated_catalog_status=protected_catalog,
                        authenticated_catalog_tested=False, physical_camera_tested=False,
                        physical_flash_tested=False, method='Public GET requests only')
            (OUT/'report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report))
            if (web_health,backend_health,protected_catalog)!=(200,200,401):
                raise SystemExit('Unexpected HTTP boundary or health result')
            break
    except (OSError,ValueError) as error:
        print(type(error).__name__+' during bounded public read')
    time.sleep(15)
else:
    (OUT/'report.json').write_text(json.dumps({'public_assets_verified':False,'authenticated_catalog_tested':False}))
    raise SystemExit('New public assets not observed in the check window')
