/** Deterministic scan resolution. No OCR, merchant guessing or code repair. */
export type ScanCandidate = { format: string; code: string; image?: string };

function validGtin(code: string, length: number): boolean {
  if (code.length !== length || !/^[0-9]+$/.test(code)) return false;
  let total = 0;
  for (let i = code.length - 2, weight = 3; i >= 0; i--, weight = 4 - weight) total += Number(code[i]) * weight;
  return (10 - total % 10) % 10 === Number(code[code.length - 1]);
}

/**
 * UPC-A and EAN-13 with ONE leading zero encode identical physical bars.
 * ZXing may return both for one photo. They are one choice, not two cards.
 * Prefer the full EAN representation when present; never trim digits on
 * arbitrary codes, never merge QR/Code128 with numeric EAN content.
 */
export function collapseScanCandidates<T extends ScanCandidate>(candidates: readonly T[]): T[] {
  const unique = new Map<string, T>();
  for (const candidate of candidates) {
    let key = JSON.stringify([candidate.format, candidate.code]);
    if (candidate.format === 'EAN_13' && candidate.code.startsWith('0') && validGtin(candidate.code, 13)) {
      key = 'EAN_UPC:' + candidate.code;
    } else if (candidate.format === 'UPC_A' && validGtin(candidate.code, 12)) {
      key = 'EAN_UPC:0' + candidate.code;
    }
    const previous = unique.get(key);
    if (!previous || (previous.format === 'UPC_A' && candidate.format === 'EAN_13')
        || (previous.format === candidate.format && !previous.image && candidate.image)) unique.set(key, candidate);
  }
  return [...unique.values()];
}

/** Only server-generated inline PNGs are previewed; never fetch image URLs. */
export function safePreview(image?: string): string | null {
  return image && image.length <= 128_000 && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(image) ? image : null;
}
