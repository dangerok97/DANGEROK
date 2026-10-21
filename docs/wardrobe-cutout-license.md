# ORA Studio Cutout — provenance and distribution gates

Model: U²-NetP, official U²-Net Apache-2.0 project by Qin et al.,
distributed as the u2netp ONNX asset in the MIT-licensed rembg releases.

Source: https://github.com/xuebinqin/U-2-Net
Source license: https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE
Release asset: https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx
SHA256: 309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8
Expected bytes: 4,574,861.

Python model loader follows rembg U2NetP normalization concept. Reimplemented
without copying its code. MIT license: https://github.com/danielgatis/rembg/blob/main/LICENSE.
ONNX Runtime uses MIT, Pillow uses HPND, FastAPI uses MIT.

Do not substitute BRIA-RMBG 2.0 or withoutBG's changing weight license
without a specific weight-level commercial right.

The studio cutout is NOT automatically accepted, and the original normalized
photo is never replaced. Edge accuracy must be checked against product photos
before enabling this experimental worker in the production backend.
