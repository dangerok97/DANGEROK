"""Build-time pinned U²-NetP model loader: no runtime network access."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
SHA = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
SIZE = 4_574_861
target = Path("/opt/ora-cutout/u2netp.onnx")
target.parent.mkdir(parents=True, exist_ok=True)
if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA:
    print("Pinned model verified")
else:
    with urlopen(MODEL_URL, timeout=45) as stream:
        data = stream.read(SIZE + 1)
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA:
        raise RuntimeError("Cutout model verification failed")
    target.write_bytes(data)
    print("Pinned model downloaded and verified")
