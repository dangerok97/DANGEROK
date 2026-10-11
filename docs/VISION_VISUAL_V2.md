# Vision V2 — component focus and camera-first layout

## Scope

The user approved the first visual milestone: more room for the object, clearer components, close-up on selection, zoom and rotation. This revision changes only the web presentation and its tests. No database migration, new runtime dependencies, new provider or user data access.

## Experience

The camera remains live. After recognition, the exploded schematic remains screen-anchored even when the object leaves the image. A visible X clears the result and resumes recognition on the same stream. Backgrounding or leaving the page still stops the camera. Automatic generic catalog policy remains unchanged.

The initial result opens as a whole-object view without a long explanation panel. Tapping a visible component or its corresponding labeled button brings that component forward; the remaining components shrink into a dim context view. `Vista d’insieme` returns without another recognition request. Selection opens a concise function explanation; `Come funziona` expands it, and the panel can collapse without dismissing the model.

Two-finger pinch and plus/minus controls change zoom. One-pointer drag rotates. Keyboard arrows, plus/minus, zero (reset zoom) and Escape (overview) provide alternatives. The opening slider interpolates assembly/explosion; the existing Ricomponi/Scomponi control remains.

## Implementation

- `presentation.ts`: meshes are built once from the current catalog manifest; hollow shells, raised keypad controls, richer PCB surfaces, mild perspective and shaded translucent-style surfaces. Picking uses projected faces and edge distance, not just bounding boxes.
- `gestures.ts`: bounded zoom, pointer identity bookkeeping, cancellation and prevention of accidental taps after pinch gestures; time-based easing.
- `LiveExplorer.web.tsx`: existing recognition and catalog path, screen-held model, close/reset lifecycle, focus state and compact controls. Render at most about 30 times per second during interactions; avoid repainting an unchanged scene. Video is a separate element and continues independently.
- `visualStyle.ts`: mobile-first fixed viewport, camera-heavy layout, explanatory panel shown on request, short-height/landscape rules and reduced-motion support.
- Regression tests: existing held-camera/X tests plus V2 geometry/picking/gesture tests and desktop/mobile Chromium and mobile WebKit presentation tests.

The original `scene.ts` geometry contract remains compatible. Stored manifests are not rewritten or claimed more accurate because their presentation improves.

## Acceptance / evidence

Required before release: full TypeScript check, Expo web build, dedicated Vision regression workflow, visual inspection of whole-object and focused screenshots, close/reset/no-extra-scan tests, and matching deployed commit. Test screenshots of the built app are not concept images, but tests with synthetic video/authentication are not evidence of a physical iPhone camera or live AI accuracy. Record actual workflow/deployment outcomes on the release PR; do not call them passed while pending.

## Remaining limits

Schematic family-level components, not exact parts of the photographed model. No object segmentation, realistic reconstruction from a photo, semantic correctness certification, world-anchored AR or animation of actual electrical/mechanical operation in this milestone. Native camera remains outside this web-only change. Surface picking uses projected geometry, not a full WebGL depth-buffer engine. Verify performance and gestures on real target phones before claiming device-wide quality.

## Technical references checked

- W3C Pointer Events: https://www.w3.org/TR/pointerevents3/
- MDN pinch gesture handling: https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events/Pinch_zoom_gestures
- MDN canvas optimization: https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas
