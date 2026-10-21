# ORA Foto Vetrina — experimental mask compositor (not user facing)

## Purpose
Prepare image-without-background generation for one garment image at a time,
without downloading an unvetted AI model or introducing heavy inference into
the current ORA backend.

## What exists in this experimental branch
- \`wardrobe.cutout_core.render_showcase_preview(source, model_mask)\` takes
  an EXIF-free, encrypted-at-rest wardrobe source image (decrypted in RAM) and
  a separate model-created saliency mask. It creates a 900×900 transparent
  PNG centered around the extracted foreground. This is only a preview.
- Fail-closed quality gates reject blank masks, nearly full-frame masks,
  tiny objects, heavy border contact, oversize uploads/outputs.
- Does not edit or overwrite the source; does not persist a cutout anywhere.
- Synthetic tests validate alpha/cropping and rejection. No ONNX inference is
  implemented or claimed to work yet.
- No third-party network requests, model artifacts, new dependencies,
  payment or user data. The current public ORA is untouched.

## Model candidates to evaluate on a REAL garment QA set
- \`u2netp\` (U²-Net-p), approx. 4.6MB ONNX; upstream U²-Net Apache-2.0,
  model weights described as Apache-2.0 in the candidate's model card.
  Check provenance of the *exact* ONNX conversion separately before enabling.
  A third-party candidate card reports SHA-256:
  \`309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8\`.
  Source model https://github.com/xuebinqin/U-2-Net,
  ONNX docs https://huggingface.co/edgetools/u2netp.
- \`rembg\` wrapper code MIT does NOT guarantee the terms of all model weights;
  never use default \`bria-rmbg\` automatically. BRIA models have separate
  noncommercial/commercial licensing requirements.
- Larger high-quality alternatives should be evaluated only if deployment
  memory/cost and license are acceptable to the owner.

## Next technical gates (NOT completed)
1. Implement an isolated pinned ONNX CPU inference provider after explicit
   model/weight-license and SHA256 verification.
2. Compare real garments: white on white, black on dark, shoes and thin laces,
   large prints, sleeves, and cluttered background; measure crop/edge loss.
3. Add owner-bound preview/accept/reject endpoints. Save an encrypted
   alpha PNG derivative, never overwrite the 1200px EXIF-free reference view.
4. UI shows \`Originale / Foto vetrina\`, default only after explicit acceptance.
5. Fallback: always show original if segmentation is unavailable/poor;
   no fabricated claim of a successful removal.
6. Protect CPU/memory and rate-limit generation per owner; no background
   jobs implied merely because the image was uploaded.

## Why deliberately separate
ORA's core runtime handles memory, voice, WhatsApp and autonomy. A background
removal model should not contend with those workloads unless a real pilot
demonstrates acceptable memory and latency. This branch documents and tests
the image composition contract without adding a heavyweight dependency.
