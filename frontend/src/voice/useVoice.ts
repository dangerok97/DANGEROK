/**
 * Parlare invece di scrivere.
 *
 *     IL MICROFONO DETTA. NON CONVERSA.
 *
 * Questo è il microfono del composer, e vuol dire una cosa sola: «parlo invece
 * di digitare». Le parole finiscono nel campo, partono, e ORA risponde per
 * iscritto come risponde sempre. Nessuna voce in uscita: chi ha dettato un
 * messaggio in un posto pubblico non si aspetta che la risposta gli parli.
 *
 * La conversazione a voce vera — lei parla, tu parli, senza toccare niente —
 * è `useLiveVoice`, ed è un altro pulsante perché è un'altra esperienza.
 * Tutte e due consegnano le parole alla stessa funzione, quella del testo, e
 * da lì in poi esiste un percorso solo.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import {
  VOICE_START,
  canListen,
  listen,
  nextVoice,
  spansOf,
  voiceSays,
  type Listening,
  type VoiceMark,
  type VoiceMarks,
  type VoiceState,
} from './speech';
import { unlockSpeaking } from './output';

export type UseVoice = {
  state: VoiceState;
  /** Cosa leggere sotto il microfono, o niente. */
  hint: string | null;
  /** Se questo dispositivo può ascoltare del tutto. */
  possible: boolean;
  /** Tocca il microfono: comincia, o smette. */
  toggle: () => void;
  /** Quanto è durato ogni pezzo dell'ultimo giro. */
  marks: VoiceMarks;
};

export function useVoice(opts: {
  /** La stessa funzione che manda quello che viene scritto. */
  speak: (words: string) => void | Promise<void>;
  /** Vero mentre ORA sta ragionando: il microfono non ricomincia da solo. */
  busy?: boolean;
}): UseVoice {
  const [state, fire] = useReducer(nextVoice, VOICE_START);
  const session = useRef<Listening | null>(null);
  const marks = useRef<VoiceMarks>({});
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      session.current?.cancel();
    };
  }, []);

  const mark = useCallback((what: VoiceMark) => {
    marks.current[what] = Date.now();
    if (typeof window !== 'undefined') {
      // Una finestra su dove va il tempo, per chi sta guardando. Nessuna
      // soglia, nessun avviso: solo i numeri.
      (window as any).__oraVoice = {
        marks: { ...marks.current },
        spans: spansOf(marks.current),
      };
    }
  }, []);

  const hear = useCallback(
    (words: string) => {
      mark('transcript');
      fire({ type: 'heard', words });
      const said = words.trim();
      if (!said) return;
      mark('asked');
      fire({ type: 'sent' });
      void Promise.resolve(opts.speak(said));
      fire({ type: 'done' });
    },
    [mark, opts],
  );

  const start = useCallback(() => {
    if (!canListen()) {
      fire({ type: 'trouble', why: 'not_supported' });
      return;
    }
    // Il tocco è l'unico momento in cui iOS lascia sbloccare la voce, e la
    // conversazione parlata comincia spesso da qui.
    unlockSpeaking();
    marks.current = {};
    mark('mic');
    fire({ type: 'ask' });
    session.current = listen({
      onHearing: (words) => alive.current && fire({ type: 'hearing', words }),
      onEndOfSpeech: () => mark('end_of_speech'),
      onHeard: (words) => {
        session.current = null;
        if (alive.current) hear(words);
      },
      onTrouble: (why) => {
        session.current = null;
        if (alive.current) fire({ type: 'trouble', why });
      },
    });
    if (session.current) fire({ type: 'allowed' });
  }, [hear, mark]);

  const toggle = useCallback(() => {
    if (state.phase === 'listening' || state.phase === 'asking') {
      // Ha finito di parlare e lo dice col dito: si chiude e si manda quello
      // che si è sentito, senza aspettare il silenzio.
      session.current?.stop();
      return;
    }
    if (opts.busy) return;
    start();
  }, [opts.busy, start, state.phase]);

  const hint = useMemo(() => voiceSays(state), [state]);

  return {
    state,
    hint,
    possible: canListen(),
    toggle,
    marks: marks.current,
  };
}
