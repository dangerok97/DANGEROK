"""Public image transport retry only; never uploads or stores private screenshots."""
import base64, io
from urllib.parse import urlparse, urlencode
import httpx
from PIL import Image, ImageOps
import vision_provider_live_check as smoke

PHOTO='https://thumb.wikimedia.org/wikipedia/commons/thumb/5/55/Beldray_pedal_bin.jpg/960px-Beldray_pedal_bin.jpg?utm_source=commons.wikimedia.org&utm_campaign=index&utm_content=thumbnail&_=20211111142422'
def load_photo(client):
    urls=[PHOTO,'https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Beldray_pedal_bin.jpg/960px-Beldray_pedal_bin.jpg',
          'https://wsrv.nl/?'+urlencode({'url':PHOTO,'w':960,'output':'jpg'})]
    for url in urls:
        try:
            response=client.get(url,follow_redirects=True,timeout=25)
            smoke.record('public_photo_transport',host=urlparse(url).hostname,status=response.status_code)
            if response.status_code!=200:continue
            with Image.open(io.BytesIO(response.content)) as original:
                frame=ImageOps.exif_transpose(original).convert('RGB');frame.thumbnail((960,960));out=io.BytesIO();frame.save(out,'JPEG',quality=80)
            smoke.record('public_photo_loaded',width=frame.width,height=frame.height)
            return base64.b64encode(out.getvalue()).decode()
        except (httpx.HTTPError,OSError) as exc:
            smoke.record('public_photo_transport_error',host=urlparse(url).hostname,error_type=type(exc).__name__)
    raise RuntimeError('Verified public thumbnail unavailable; no account created')
smoke.load_photo=load_photo
if __name__=='__main__':
    try:smoke.main()
    except Exception as exc:
        smoke.record('failed',error_type=type(exc).__name__,message=str(exc)[:160]);raise SystemExit(1)
