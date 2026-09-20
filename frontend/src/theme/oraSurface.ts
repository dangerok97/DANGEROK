/**
 * ORA Quiet Premium — la grammatica visiva del rebuild V3.21.3.
 *
 * Un posto solo per i valori che le cinque reference approvate hanno in
 * comune: il bianco caldo del fondo, il blu profondo della gerarchia, il blu
 * luminoso riservato a CTA e stato attivo, il verde del successo, l'arancio
 * tenue dell'attenzione, i grigi blu dei testi secondari, bordi quasi
 * invisibili e ombre appena percettibili. Le schermate non scrivono colori
 * propri: prendono questi.
 */
import { Platform, type ViewStyle } from 'react-native';

export const ora = {
  // fondo e superfici
  canvas: '#F7F6F3',          // il bianco caldo della pagina e della barra
  surface: '#FFFFFF',
  surfaceWarm: '#FBF7F1',     // la card eroe
  surfaceTint: '#F3F6FB',     // inserti azzurrati (insight, riepiloghi)
  hairline: '#E6E3DD',        // bordo delle card
  divider: '#EEEBE6',         // separatori fra righe

  // testo
  ink: '#141B2D',             // titoli: blu notte quasi nero
  ink2: '#4A5468',            // corpo secondario, blu-grigio
  ink3: '#6B7384',            // didascalie
  deep: '#1B2B5E',            // blu ORA profondo per la gerarchia

  // azione e stato
  cta: '#1F5FD9',             // l'unico blu luminoso: CTA e stato attivo
  ctaPressed: '#194FB8',
  activeBg: '#E9F0FC',        // pillola della voce corrente
  hover: '#F0EEEA',
  ctaSoftBorder: '#B9CDF3',   // bottoni secondari bordati di blu

  success: '#1E8A4C',
  successBg: '#E6F4EC',
  attention: '#C77A12',
  attentionBg: '#FDF2E1',
  neutralBg: '#F1EFEB',

  radius: { card: 22, inner: 16, control: 12, pill: 999 },
  space: { page: 32, gap: 20, card: 24 },
} as const;

/** L'ombra delle card: c'è, ma non si nota. */
export const oraShadow: ViewStyle =
  Platform.OS === 'web'
    ? ({ boxShadow: '0 1px 2px rgba(20, 27, 45, 0.04), 0 4px 16px rgba(20, 27, 45, 0.03)' } as any)
    : {
        shadowColor: '#141B2D',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.05,
        shadowRadius: 10,
        elevation: 1,
      };

export const oraType = {
  display: { fontSize: 36, lineHeight: 44, fontWeight: '700' as const, letterSpacing: -0.4 },
  hero: { fontSize: 28, lineHeight: 34, fontWeight: '700' as const, letterSpacing: -0.2 },
  title: { fontSize: 20, lineHeight: 26, fontWeight: '600' as const },
  section: { fontSize: 18, lineHeight: 24, fontWeight: '600' as const },
  body: { fontSize: 15, lineHeight: 22 },
  small: { fontSize: 13, lineHeight: 18 },
  eyebrow: { fontSize: 12, lineHeight: 16, fontWeight: '600' as const, letterSpacing: 1 },
};
