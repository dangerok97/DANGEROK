#!/bin/sh
# BodyParts3D 4.0 reference atlas built from a pinned open-source distribution.
# No biometric photographs or user data enter this build step.
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

SOURCE_SHA="1c38bf35c254a891200d3cedecfd57abebe83d8d"
SOURCE_URL="https://github.com/ashemag/human-atlas.git"
DESTINATION="${1:-/vendor/bodyparts3d}"
mkdir -p "$DESTINATION"
git -C "$DESTINATION" init -q
git -C "$DESTINATION" remote add origin "$SOURCE_URL"
git -C "$DESTINATION" fetch -q --depth 1 origin "$SOURCE_SHA"
git -C "$DESTINATION" checkout -q --detach FETCH_HEAD
test "$(git -C "$DESTINATION" rev-parse HEAD)" = "$SOURCE_SHA"
cd "$DESTINATION"

# Copy static geometry to an ORA namespaced path. No external runtime CDN.
node <<'NODE'
const fs = require('node:fs');
const manifestPath = 'public/models/atlas.json';
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
if (manifest.version !== 'BodyParts3D 4.0' || manifest.parts.length < 2200 ||
    manifest.concepts.length < 3400 || manifest.chunks.length < 10) {
  throw new Error('The pinned source anatomy manifest differs from the reviewed reference');
}
for (const chunk of manifest.chunks) {
  for (const key of ['url','gzip']) {
    if (typeof chunk[key] === 'string') {
      if (!chunk[key].startsWith('/models/')) throw new Error('Unexpected anatomy asset path');
      chunk[key] = '/bodyparts3d' + chunk[key];
    }
  }
}
fs.writeFileSync(manifestPath, JSON.stringify(manifest));
const pagePath = 'app/page.tsx';
const page = fs.readFileSync(pagePath, 'utf8');
const from = "fetch('/models/atlas.json'";
if (!page.includes(from)) throw new Error('Cannot namespace the upstream anatomy catalogue path');
fs.writeFileSync(pagePath, page.replace(from, "fetch('/bodyparts3d/models/atlas.json'"));
const htmlPath = 'web/index.html';
const html = fs.readFileSync(htmlPath, 'utf8');
fs.writeFileSync(htmlPath, html.replace('href="/favicon.svg"', 'href="/bodyparts3d/favicon.svg"'));
NODE

# Adapt only the pinned source viewer. Preserve meshes, FMA IDs, credits and licenses.
node "$SCRIPT_DIR/ora-bodyparts3d-patch.mjs" "$DESTINATION" "$SCRIPT_DIR"

# npm CI uses the upstream committed lockfile; Node.js >=22.13 is required.
npm ci --no-audit --no-fund
npm run check
npm run build -- --base=/bodyparts3d/
test -s dist/index.html
test -s dist/models/atlas.json
test -s dist/models/body-0.bin.gz
test -s dist/ATTRIBUTION.md
cp LICENSE dist/UPSTREAM_MIT_LICENSE.txt
node <<'NODE'
const fs = require('node:fs');
const path = 'dist/ora-integrated.json';
const data = {
  provider:'BodyParts3D',
  dataset_version:'4.0',
  license:'CC BY 4.0',
  source_archive:'isa_BP3D_4.0_obj_99.zip',
  reference:'adult male',
  model_is_person_specific:false,
  provenance:'BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International',
  distributor:'ashemag/human-atlas',
  distributor_commit:'1c38bf35c254a891200d3cedecfd57abebe83d8d',
  parts:2234,
  concepts:3432,
  attribution_url:'/bodyparts3d/ATTRIBUTION.md',
  original_license_url:'https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html'
};
const manifest=JSON.parse(fs.readFileSync('dist/models/atlas.json','utf8'));
if(data.parts!==manifest.parts.length||data.concepts!==manifest.concepts.length){
 throw new Error('Actual anatomy model counts mismatch');
}
fs.writeFileSync(path,JSON.stringify(data));
console.log(JSON.stringify({integration:'BodyParts3D 4.0',parts:data.parts,concepts:data.concepts,chunks:manifest.chunks.length,source:data.distributor_commit}));
NODE
