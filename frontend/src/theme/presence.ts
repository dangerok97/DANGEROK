/** Approved ORA presence palette; isolated from the readable conversation. */
export const presencePalette = {"background": "#06090e", "atmosphere": "#0c151e", "depth": "#080d14", "warmLabel": "#e3c492", "label": "#9fced9", "warmGlow": "255,211,157", "glow": "183,238,247", "dust": "163,196,207", "warmEdge": "236,204,154", "edge": "169,219,231", "trail": "190,235,245", "warmPacket": "255,225,179", "packet": "219,251,255", "warmPoint": "255,238,201", "point": "234,255,255", "warmNode": "255,232,187", "node": "213,242,247", "temporaryGlow": "255,72,72", "temporaryNode": "255,92,92", "temporaryPoint": "255,176,176", "cross": "219,246,250", "leader": "146,200,211", "labelBackground": "rgba(6,9,14,.66)", "text": "#e4edf0", "muted": "#a4b6c0", "border": "#2b3641"} as const;

/** The conversation surface shares the map palette, scoped to ORA only. */
export const presenceColors = {
  backgroundPrimary: presencePalette.background, backgroundSecondary: presencePalette.depth,
  surface: presencePalette.atmosphere, surfaceWarm: presencePalette.atmosphere,
  surfaceElevated: presencePalette.depth, surfaceGlass: 'rgba(12,21,30,.94)',
  textPrimary: presencePalette.text, textSecondary: presencePalette.muted,
  textTertiary: presencePalette.muted, placeholder: presencePalette.muted,
  border: presencePalette.border, divider: presencePalette.border,
  accent: presencePalette.label, onAccent: presencePalette.background,
} as const;
