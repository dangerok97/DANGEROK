#!/bin/sh
# Make the single-page web export installable on the iPhone Home Screen.
# With web.output "single", Expo ignores app/+html.tsx and does not copy
# public/, so the manifest, icons, service worker and Home Screen meta tags
# never reached production (23/10/2026). Done here, after the export.
set -eu
DIST="${1:-dist}"
cp -R public/. "$DIST/"
TAGS='<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="ORA"><meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="theme-color" content="#0A122C">'
grep -q 'rel="manifest"' "$DIST/index.html" || sed -i "s|</head>|${TAGS}</head>|" "$DIST/index.html"
for f in sw.js manifest.webmanifest apple-touch-icon.png icon-192.png icon-512.png; do
  test -s "$DIST/$f" || { echo "missing $f in $DIST" >&2; exit 1; }
done
grep -q 'rel="manifest"' "$DIST/index.html" || { echo "manifest link not injected" >&2; exit 1; }
echo "PWA files ready in $DIST"
