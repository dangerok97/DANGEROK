/** Viewport budgeting for the mobile conversation. No content or domain routing. */
export function mobileConversationLayout(height: number, editing: boolean) {
  const available = Number.isFinite(height) && height > 0 ? height : 640;
  // The preview is optional, never the chat. Short windows / keyboard get no map.
  const previewHeight = editing || available < 470
    ? 0
    : Math.round(Math.min(128, Math.max(76, available * 0.17)));
  return { previewHeight, showPreview: previewHeight > 0 };
}

export function remainingVisualHeight(viewportHeight: number, offsetTop: number, rootTop: number, bottomInset = 0): number | null {
  if (![viewportHeight, offsetTop, rootTop, bottomInset].every(Number.isFinite) || viewportHeight <= 0) return null;
  // A parent may contain contextual chrome; do not cover it with a fixed overlay.
  return Math.max(0, Math.floor(viewportHeight - Math.max(0, rootTop - offsetTop) - Math.max(0, bottomInset)));
}
