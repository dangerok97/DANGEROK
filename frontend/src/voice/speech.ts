/**
 * La voce come modo di parlare con ORA, non come un secondo assistente.
 *
 *     VOICE IS NOT A SEPARATE ASSISTANT.
 *
 * Qui dentro non c'è nessuna intelligenza: non si decide cosa rispondere, non
 * si cerca niente nella vita di nessuno e non si tiene nessuna memoria. Il
 * microfono produce delle parole e quelle parole entrano nella stessa
 * conversazione dove entrerebbero se fossero state scritte — stessa sessione,
 * stesso agente, stessa autorità. L'unica cosa che questo file sa fare è
 * ascoltare, dire, e raccontare a che punto è.
 *
 * Quello che segue è diviso in due metà per una ragione precisa. La metà pura
 * — come si legge una frase ad alta voce, come si passa da uno stato
 * all'altro, quanto è durato ogni pezzo — si può provare senza un microfono e
 * senza un browser, ed è dove stanno gli errori veri. La metà che tocca il
 * dispositivo è sottile apposta: se un giorno l'ascolto arriverà dal server
 * invece che dal browser, è l'unica parte da riscrivere.
 *
 * Chi parla, invece, sta in `output.ts`: dire una frase e sentirla dire sono
 * due mestieri diversi, e tenerli nello stesso file ha smesso di avere senso
 * il giorno in cui la voce di ORA ha smesso di essere per forza quella del
 * browser.
 */

/** Dove siamo, in parole che una persona potrebbe leggere. */
export type VoicePhase =
  | 'idle'
  | 'asking'
  | 'listening'
  | 'heard'
  | 'thinking'
  // La risposta c'e' e l'audio non e' ancora partito. E' uno stato suo, e non
  // e' un dettaglio: chiamarlo «sta parlando» significa dire che si sente una
  // voce mentre non si sente niente, e chi ha appena finito di parlare resta
  // in silenzio a chiedersi se il microfono lo ha sentito.
  | 'preparing'
  | 'speaking'
  | 'blocked';

export type VoiceState = {
  phase: VoicePhase;
  /** Quello che sta dicendo adesso, mentre lo dice. */
  interim: string;
  /** Quello che ha detto, quando ha finito di dirlo. */
  said: string;
  /** Perché non si può, quando non si può. */
  trouble: string | null;
};

export const VOICE_START: VoiceState = {
  phase: 'idle',
  interim: '',
  said: '',
  trouble: null,
};

export type VoiceEvent =
  | { type: 'ask' }
  | { type: 'allowed' }
  | { type: 'hearing'; words: string }
  | { type: 'heard'; words: string }
  | { type: 'sent' }
  | { type: 'answered' }
  | { type: 'speaking' }
  | { type: 'done' }
  | { type: 'quiet' }
  | { type: 'trouble'; why: VoiceTrouble };

/**
 * Cosa può andare storto, e come si dice.
 *
 * Nessuna di queste è un errore di sistema da mostrare: sono situazioni
 * normali di un microfono in mano a una persona, e ognuna ha una via d'uscita
 * che è sempre la stessa — si può scrivere.
 */
export type VoiceTrouble =
  | 'no_permission'
  | 'no_microphone'
  | 'not_supported'
  | 'heard_nothing'
  | 'could_not_understand'
  | 'network'
  | 'cannot_speak';

const TROUBLE_SAYS: Record<VoiceTrouble, string> = {
  no_permission: 'Non ho accesso al microfono. Puoi scrivermi, oppure darmi il permesso dalle impostazioni del browser.',
  no_microphone: 'Non trovo un microfono. Scrivimi pure.',
  not_supported: 'Su questo browser non riesco ad ascoltare. Scrivimi pure.',
  heard_nothing: 'Non ho sentito niente.',
  could_not_understand: 'Non ho capito bene. Riprova, o scrivimelo.',
  network: 'Non riesco a sentirti adesso. Scrivimi pure.',
  cannot_speak: '',
};

/** Cosa leggere sotto il microfono, in italiano e senza gergo. */
export function voiceSays(state: VoiceState): string | null {
  if (state.trouble) return TROUBLE_SAYS[state.trouble as VoiceTrouble] || null;
  switch (state.phase) {
    case 'asking':
      return 'Un momento…';
    case 'listening':
      return 'Ti ascolto';
    case 'heard':
    case 'thinking':
    case 'preparing':
      return 'Sto ragionando…';
    case 'speaking':
      return null;
    default:
      return null;
  }
}

/**
 * Come si passa da uno stato all'altro.
 *
 * Un riduttore e non un insieme di `setState` sparsi, perché gli stati di una
 * conversazione a voce si accavallano: la persona ricomincia a parlare mentre
 * ORA sta ancora parlando, la risposta arriva mentre il microfono è già
 * chiuso, il permesso viene negato a metà. Tenerli in un posto solo è l'unico
 * modo di poterli provare tutti.
 */
export function nextVoice(state: VoiceState, event: VoiceEvent): VoiceState {
  switch (event.type) {
    case 'ask':
      return { ...VOICE_START, phase: 'asking' };
    case 'allowed':
      return { ...state, phase: 'listening', trouble: null };
    case 'hearing':
      return { ...state, phase: 'listening', interim: event.words };
    case 'heard': {
      const words = event.words.trim();
      if (!words) return { ...state, phase: 'idle', interim: '', trouble: 'heard_nothing' };
      return { ...state, phase: 'heard', interim: '', said: words };
    }
    case 'sent':
      return { ...state, phase: 'thinking' };
    case 'answered':
      return { ...state, phase: 'preparing' };
    case 'speaking':
      return { ...state, phase: 'speaking' };
    case 'done':
      return { ...state, phase: 'idle', interim: '' };
    case 'quiet':
      // Chi tocca il microfono mentre ORA parla vuole parlare, non spegnere.
      return { ...state, phase: 'idle', interim: '' };
    case 'trouble':
      return {
        ...state,
        phase: event.why === 'no_permission' || event.why === 'not_supported'
          ? 'blocked'
          : 'idle',
        interim: '',
        trouble: event.why,
      };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Le parole degli stati, per la conversazione parlata
//
// Stanno qui e non nel ciclo perche' sono la parte pura: si possono
// provare tutte, una per una, senza un microfono e senza un browser — ed e'
// esattamente dove si sbaglia, perche' «ORA sta parlando» detto un attimo
// troppo presto e' una promessa che a volte non si mantiene.
// ---------------------------------------------------------------------------

/** Cosa succede adesso, in parole che una persona direbbe. */
export function saying(state: VoiceState, muted: boolean, stuck: boolean): string {
  if (stuck) return 'Non è arrivata risposta';
  if (muted) return 'Microfono in pausa';
  switch (state.phase) {
    case 'asking':
      return 'Un momento…';
    case 'listening':
      return 'Ti ascolto';
    case 'heard':
    case 'thinking':
      return 'Sto pensando';
    case 'preparing':
      return 'Sto per rispondere';
    case 'speaking':
      return 'ORA sta parlando';
    case 'blocked':
      return 'Non riesco ad ascoltare';
    default:
      return 'Tocca per parlare';
  }
}

/** La riga sotto, quando aggiunge qualcosa. Altrimenti niente. */
export function hinting(
  state: VoiceState, muted: boolean, stuck: boolean, readable: boolean,
): string | null {
  if (stuck) return 'Puoi riprovare, oppure chiudere e scrivermi.';
  if (muted) return 'Riaccendilo quando vuoi parlare.';
  if (state.phase === 'blocked') return 'Chiudi e scrivimi pure: è lo stesso discorso.';
  if (readable) return 'Non riesco a dirtela ad alta voce: la trovi scritta qui dietro.';
  if (state.phase === 'speaking' || state.phase === 'preparing') {
    return 'Tocca per interromperla.';
  }
  return null;
}


/**
 * La stessa risposta, detta invece che letta.
 *
 *     TESTO E VOCE NON DEVONO DIVERGERE.
 *
 * Non è un riassunto e non è un'altra risposta: sono le stesse parole senza
 * quello che esiste solo sulla pagina. Un asterisco non si pronuncia, un
 * indirizzo web letto ad alta voce è un rumore lungo, e un elenco puntato
 * detto senza pause diventa una frase sola che non si capisce.
 */
export function forSpeaking(text: string): string {
  let out = (text || '').trim();
  if (!out) return '';
  // I link diventano il loro testo: nessuno ascolta un URL.
  out = out.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  out = out.replace(/https?:\/\/\S+/g, '');
  // Enfasi, titoli e citazioni sono composizione, non parole.
  out = out.replace(/[*_`#>]+/g, '');
  // Un elenco è una serie di frasi: si dicono una alla volta.
  out = out.replace(/^\s*[-•·]\s+/gm, '');
  out = out.replace(/\n{2,}/g, '. ');
  out = out.replace(/\n/g, '. ');
  out = out.replace(/\s{2,}/g, ' ');
  out = out.replace(/\.\s*\./g, '.');
  // E poi la forma pronunciabile: una data diventa un giorno e un mese, una
  // cifra diventa un numero. Stesso significato, altra forma — non si
  // aggiunge e non si toglie niente.
  return pronounceable(out.trim());
}

// ---------------------------------------------------------------------------
// La stessa frase, scritta per essere detta
//
//     STESSO SIGNIFICATO, ALTRA FORMA.
//     NON SI AGGIUNGE E NON SI TOGLIE NIENTE.
//
// «Il 20/09 alle 06:00» sullo schermo si legge in un colpo d'occhio. Detto
// ad alta voce da una macchina che pronuncia i caratteri diventa «il venti
// barra zero nove alle zero sei due punti zero zero», che nessuno direbbe
// mai e che è più difficile da capire di quanto sia stato veloce da
// scrivere.
//
// Quindi una data diventa un giorno e un mese, un'ora diventa un'ora, una
// cifra diventa un numero e un indirizzo web smette di essere sillabato. Il
// significato resta identico: non si arrotonda, non si riassume, non si
// spiega niente in più. Se una trasformazione non è sicura non si fa — dire
// la cosa scritta è sempre meglio che dire una cosa diversa.
// ---------------------------------------------------------------------------

const MESI = [
  'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
  'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre',
];

const UNITA = [
  '', 'uno', 'due', 'tre', 'quattro', 'cinque', 'sei', 'sette', 'otto', 'nove',
  'dieci', 'undici', 'dodici', 'tredici', 'quattordici', 'quindici', 'sedici',
  'diciassette', 'diciotto', 'diciannove',
];

const DECINE = [
  '', '', 'venti', 'trenta', 'quaranta', 'cinquanta',
  'sessanta', 'settanta', 'ottanta', 'novanta',
];

/**
 * Un numero come lo direbbe qualcuno, fino a un milione.
 *
 * Oltre non si prova nemmeno: le cifre di un numero enorme lette a voce non
 * le segue nessuno, e sbagliarne una è peggio che lasciarlo scritto.
 */
export function inParole(n: number): string | null {
  if (!Number.isInteger(n) || n < 0 || n >= 1_000_000) return null;
  if (n === 0) return 'zero';

  const sotto100 = (v: number): string => {
    if (v < 20) return UNITA[v];
    const d = Math.floor(v / 10);
    const u = v % 10;
    let testa = DECINE[d];
    // «ventuno», non «ventiuno»; «ventotto», non «ventiotto».
    if (u === 1 || u === 8) testa = testa.slice(0, -1);
    return u ? testa + UNITA[u] : testa;
  };

  const sotto1000 = (v: number): string => {
    const c = Math.floor(v / 100);
    const resto = v % 100;
    if (!c) return sotto100(resto);
    const testa = c === 1 ? 'cento' : `${UNITA[c]}cento`;
    return resto ? testa + sotto100(resto) : testa;
  };

  const migliaia = Math.floor(n / 1000);
  const resto = n % 1000;
  if (!migliaia) return sotto1000(resto);
  const testa = migliaia === 1 ? 'mille' : `${sotto1000(migliaia)}mila`;
  return resto ? `${testa}${sotto1000(resto)}` : testa;
}

/** Un'ora come la direbbe qualcuno: «alle sei», «alle dieci e trenta». */
function ora(h: number, m: number): string | null {
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  const ore = inParole(h);
  if (!ore) return null;
  if (m === 0) return ore;
  if (m === 30) return `${ore} e mezza`;
  if (m === 15) return `${ore} e un quarto`;
  const minuti = inParole(m);
  return minuti ? `${ore} e ${minuti}` : null;
}

/**
 * La frase, pronunciabile.
 *
 * Ogni sostituzione è ancorata a una forma che non lascia dubbi: una data con
 * le barre, un orario con i due punti, una cifra con il simbolo dell'euro.
 * Quello che non corrisponde a una di queste resta esattamente com'è.
 */
export function pronounceable(text: string): string {
  let out = text || '';
  if (!out.trim()) return '';

  // Un indirizzo web non si sillaba: se ne dice l'esistenza e basta, perché
  // toglierlo del tutto cambierebbe quello che è stato detto.
  out = out.replace(/https?:\/\/\S+/gi, 'un link');
  out = out.replace(/\bwww\.\S+/gi, 'un link');

  // 12/09/2026 e 12-09-2026 → «dodici settembre duemilaventisei»
  out = out.replace(
    /\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b/g,
    (whole, d, m, y) => {
      const giorno = inParole(Number(d));
      const mese = MESI[Number(m) - 1];
      const anno = inParole(Number(y));
      return giorno && mese && anno ? `${giorno} ${mese} ${anno}` : whole;
    },
  );

  // 20/09 → «venti settembre»
  out = out.replace(/\b(\d{1,2})\/(\d{1,2})\b(?!\/)/g, (whole, d, m) => {
    const giorno = inParole(Number(d));
    const mese = MESI[Number(m) - 1];
    return giorno && mese ? `${giorno} ${mese}` : whole;
  });

  // 4.000 € · €2.050 · 4000 euro → «quattromila euro»
  const soldi = (raw: string): string | null => {
    const clean = raw.replace(/\./g, '').replace(',', '.');
    const value = Number(clean);
    if (!Number.isFinite(value)) return null;
    const intero = Math.trunc(value);
    const centesimi = Math.round((value - intero) * 100);
    const parte = inParole(intero);
    if (!parte) return null;
    if (!centesimi) return `${parte} euro`;
    const cent = inParole(centesimi);
    return cent ? `${parte} euro e ${cent}` : null;
  };
  const CIFRA = /\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?/;
  out = out.replace(
    new RegExp(`€\\s?(${CIFRA.source})`, 'g'),
    (whole, n) => soldi(n) ?? whole,
  );
  out = out.replace(
    new RegExp(`(${CIFRA.source})\\s?€`, 'g'),
    (whole, n) => soldi(n) ?? whole,
  );
  out = out.replace(
    new RegExp(`\\b(${CIFRA.source})\\s?euro\\b`, 'gi'),
    (whole, n) => soldi(n) ?? whole,
  );

  // 06:00 → «sei» · 10:30 → «dieci e mezza»
  out = out.replace(/\b(\d{1,2}):(\d{2})\b/g, (whole, h, m) => {
    return ora(Number(h), Number(m)) ?? whole;
  });

  // Le abbreviazioni che una voce sillaberebbe lettera per lettera.
  const SCORCIATOIE: Array<[RegExp, string]> = [
    [/\becc\./gi, 'eccetera'],
    [/\bes\./gi, 'esempio'],
    [/\bca\.\s/gi, 'circa '],
    [/\bn\.\s?(?=\d)/gi, 'numero '],
  ];
  for (const [pattern, replacement] of SCORCIATOIE) {
    out = out.replace(pattern, replacement);
  }

  // Numeri rimasti soli, entro un limite. Le cifre di un anno o di un codice
  // non si toccano: «PNR VPKY35» detto a parole non lo riconoscerebbe
  // nessuno, e un numero di quattro cifre attaccato a delle lettere non è un
  // numero, è un'etichetta.
  out = out.replace(/(?<![\w:/,.-])(\d{1,4})(?![\w:/-]|[.,]\d)/g, (whole, n) => {
    const value = Number(n);
    if (value >= 1900 && value <= 2100) return whole; // sembra un anno
    return inParole(value) ?? whole;
  });

  return out.replace(/\s{2,}/g, ' ').trim();
}


/**
 * Quanto è durato ogni pezzo, dal microfono alla voce.
 *
 * Misurato e basta. Non c'è nessuna soglia qui dentro e nessun avviso: sapere
 * dove va il tempo è la condizione per poterlo togliere un giorno, e
 * ottimizzare prima di saperlo è come indovinare.
 */
export type VoiceMarks = Partial<Record<VoiceMark, number>>;

export type VoiceMark =
  | 'mic'
  | 'end_of_speech'
  | 'transcript'
  | 'asked'
  | 'answer'
  | 'speech';

const SPANS: Array<[string, VoiceMark, VoiceMark]> = [
  ['ascolto', 'mic', 'end_of_speech'],
  ['trascrizione', 'end_of_speech', 'transcript'],
  ['invio', 'transcript', 'asked'],
  ['ragionamento', 'asked', 'answer'],
  ['prima parola', 'answer', 'speech'],
  ['totale', 'mic', 'speech'],
];

export function spansOf(marks: VoiceMarks): Array<{ what: string; ms: number }> {
  const out: Array<{ what: string; ms: number }> = [];
  for (const [what, from, to] of SPANS) {
    const a = marks[from];
    const b = marks[to];
    if (typeof a === 'number' && typeof b === 'number' && b >= a) {
      out.push({ what, ms: Math.round(b - a) });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// La metà che tocca il dispositivo.
// ---------------------------------------------------------------------------

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
  onspeechend: (() => void) | null;
};

function recognizer(): Recognition | null {
  if (typeof window === 'undefined') return null;
  const w = window as any;
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!Ctor) return null;
  try {
    return new Ctor() as Recognition;
  } catch {
    return null;
  }
}

export function canListen(): boolean {
  return recognizer() !== null;
}

export type Listening = {
  stop: () => void;
  cancel: () => void;
};

/**
 * Ascolta finché la persona non smette di parlare.
 *
 * `onHearing` arriva mentre parla — serve a far vedere che qualcosa sta
 * succedendo — e `onHeard` una volta sola, quando ha finito. Chi chiama non
 * deve sapere niente di come funziona il riconoscimento.
 */
export function listen(opts: {
  onHearing: (words: string) => void;
  onHeard: (words: string) => void;
  onEndOfSpeech?: () => void;
  onTrouble: (why: VoiceTrouble) => void;
}): Listening | null {
  const rec = recognizer();
  if (!rec) {
    opts.onTrouble('not_supported');
    return null;
  }
  rec.lang = 'it-IT';
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  let best = '';
  let finished = false;

  rec.onresult = (e: any) => {
    let interim = '';
    let settled = '';
    for (let i = e.resultIndex; i < e.results.length; i += 1) {
      const alt = e.results[i][0]?.transcript || '';
      if (e.results[i].isFinal) settled += alt;
      else interim += alt;
    }
    if (settled) best = (best + ' ' + settled).trim();
    opts.onHearing((best + ' ' + interim).trim());
  };

  rec.onspeechend = () => {
    opts.onEndOfSpeech?.();
  };

  rec.onerror = (e: any) => {
    const kind = String(e?.error || '');
    finished = true;
    if (kind === 'not-allowed' || kind === 'service-not-allowed') opts.onTrouble('no_permission');
    else if (kind === 'audio-capture') opts.onTrouble('no_microphone');
    else if (kind === 'no-speech') opts.onTrouble('heard_nothing');
    else if (kind === 'network') opts.onTrouble('network');
    else if (kind === 'aborted') {
      /* L'ha fermato la persona: non è un guaio e non si dice niente. */
    } else opts.onTrouble('could_not_understand');
  };

  rec.onend = () => {
    if (finished) return;
    finished = true;
    opts.onHeard(best.trim());
  };

  try {
    rec.start();
  } catch {
    opts.onTrouble('not_supported');
    return null;
  }

  return {
    stop: () => {
      try {
        rec.stop();
      } catch {
        /* già finito */
      }
    },
    cancel: () => {
      finished = true;
      try {
        rec.abort();
      } catch {
        /* già finito */
      }
    },
  };
}
