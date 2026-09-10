/**
 * Una conversazione parlata: lei parla, tu parli, senza toccare niente.
 *
 *     È UNA MODALITÀ, NON UN ALTRO ASSISTENTE.
 *
 * Stessa sessione, stesso agente, stesse capacità, stessa autorità, stessa
 * memoria. L'unica cosa che cambia è che qui ORA risponde a voce e poi torna
 * ad ascoltare da sola: il giro è parla → pensa → rispondi → riascolta, e
 * finisce quando la persona lo chiude.
 *
 * Il ciclo è l'unica cosa difficile di questo file, e la parte difficile del
 * ciclo sono le risposte in ritardo. Un microfono che si riapre mentre
 * l'altoparlante suona si sente parlare addosso; un audio che parte dopo che
 * qualcuno ha chiuso parla a una stanza vuota; una richiesta lenta che
 * torna dopo che la persona ha messo in pausa il microfono lo riaccende da
 * sola. Sono tre modi diversi di dire la stessa cosa — chi torna dal passato
 * non ha voce in capitolo sul presente — e si risolvono in un modo solo: ogni
 * giro ha un suo numero, e chi ritorna con un numero vecchio viene lasciato
 * cadere senza cambiare niente.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';

import {
  VOICE_START,
  canListen,
  forSpeaking,
  hinting,
  listen,
  nextVoice,
  saying,
  spansOf,
  type Listening,
  type VoiceMark,
  type VoiceMarks,
  type VoiceState,
} from './speech';
import { oraVoice, unlockSpeaking, type SpeechOutputProvider } from './output';

export type LiveVoice = {
  state: VoiceState;
  /** Aperta o no. Fuori di qui la conversazione è quella scritta di sempre. */
  on: boolean;
  /** Lo stato in parole, per il centro dello schermo. */
  says: string;
  /** Una riga sotto lo stato, quando c'è qualcosa di utile da dire. */
  hint: string | null;
  /** L'ultima cosa che la persona ha detto, mentre la dice. */
  heard: string;
  /** Il microfono è in pausa di proposito. */
  muted: boolean;
  /** C'è qualcosa da riprovare, e la persona può chiederlo. */
  canRetry: boolean;
  open: () => void;
  close: () => void;
  toggleMute: () => void;
  /** Tocca mentre ORA parla o si prepara: la ferma e riapre l'ascolto. */
  interrupt: () => void;
  /** Riprova l'ultima cosa detta, quando la risposta non era arrivata. */
  retry: () => void;
  /** Una risposta è arrivata: qui viene detta. */
  answered: (text: string) => void;
  /** La risposta non è arrivata affatto. */
  stumbled: () => void;
  marks: VoiceMarks;
};

export function useLiveVoice(opts: {
  /** La stessa funzione che manda quello che viene scritto. */
  speak: (words: string) => void | Promise<void>;
  /** La voce di ORA. Chi chiama non sa di chi sia. */
  voice?: SpeechOutputProvider;
}): LiveVoice {
  const [state, fire] = useReducer(nextVoice, VOICE_START);
  const [on, setOn] = useState(false);
  const [muted, setMuted] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [readable, setReadable] = useState(false);
  const session = useRef<Listening | null>(null);
  const marks = useRef<VoiceMarks>({});
  const alive = useRef(true);
  const open = useRef(false);
  const mutedRef = useRef(false);
  const waiting = useRef(false);
  const lastSaid = useRef('');
  /*
    Il numero di questo giro. Cambia a ogni cosa che rende vecchio quello che
    stava succedendo: un nuovo ascolto, un'interruzione, una pausa, la
    chiusura. Chi torna con un numero diverso da questo è in ritardo, e chi è
    in ritardo non tocca niente.
  */
  const turn = useRef(0);

  const voice = useMemo(() => opts.voice || oraVoice(defaultRequest), [opts.voice]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      open.current = false;
      turn.current += 1;
      session.current?.cancel();
      voice.stop();
    };
  }, [voice]);

  const mark = useCallback((what: VoiceMark) => {
    marks.current[what] = Date.now();
    if (typeof window !== 'undefined') {
      (window as any).__oraLiveVoice = {
        marks: { ...marks.current },
        spans: spansOf(marks.current),
      };
    }
  }, []);

  /** Se quello che sta tornando appartiene ancora a adesso. */
  const current = useCallback(
    (mine: number) => alive.current && open.current && turn.current === mine,
    [],
  );

  const startListening = useCallback(() => {
    if (!open.current || mutedRef.current || waiting.current) return;
    if (!canListen()) {
      fire({ type: 'trouble', why: 'not_supported' });
      return;
    }
    turn.current += 1;
    const mine = turn.current;
    setStuck(false);
    setReadable(false);
    marks.current = { mic: Date.now() };
    fire({ type: 'ask' });
    session.current = listen({
      onHearing: (words) => current(mine) && fire({ type: 'hearing', words }),
      onEndOfSpeech: () => current(mine) && mark('end_of_speech'),
      onHeard: (words) => {
        if (!current(mine)) return;
        session.current = null;
        mark('transcript');
        fire({ type: 'heard', words });
        const said = words.trim();
        if (!said) {
          // Silenzio. Non è un guaio e non è la fine della conversazione:
          // si riascolta, come farebbe una persona che aspetta.
          startListening();
          return;
        }
        lastSaid.current = said;
        waiting.current = true;
        mark('asked');
        fire({ type: 'sent' });
        void Promise.resolve(opts.speak(said));
      },
      onTrouble: (why) => {
        if (!current(mine)) return;
        session.current = null;
        if (why === 'heard_nothing') {
          startListening();
          return;
        }
        fire({ type: 'trouble', why });
      },
    });
    if (session.current) fire({ type: 'allowed' });
  }, [current, mark, opts]);

  const answered = useCallback(
    (text: string) => {
      if (!open.current) return;
      waiting.current = false;
      setStuck(false);
      mark('answer');
      const words = forSpeaking(text);
      if (!words) {
        startListening();
        return;
      }
      turn.current += 1;
      const mine = turn.current;
      fire({ type: 'answered' });
      void voice
        .speak(words, {
          onStart: () => {
            /*
              «ORA sta parlando» solo adesso, che l'audio è davvero partito.
              Dirlo prima — mentre il file si scarica, o mentre un provider
              ci sta provando — è una promessa che a volte non si mantiene, e
              chi la sente resta a fissare uno schermo muto.
            */
            if (!current(mine)) return;
            mark('speech');
            fire({ type: 'speaking' });
          },
        })
        .catch(() => {
          // La risposta c'è, la voce no. Sono due guai diversi e questo è il
          // meno grave: si dice che è scritta qui dietro e si va avanti.
          if (current(mine)) setReadable(true);
        })
        .finally(() => {
          if (!current(mine)) return;
          fire({ type: 'done' });
          startListening();
        });
    },
    [current, mark, startListening, voice],
  );

  const stumbled = useCallback(() => {
    /*
      La richiesta non è arrivata a destinazione — rete caduta, modello
      irraggiungibile, qualunque cosa. Non si riprova da soli: un ciclo che
      ritenta all'infinito davanti a un servizio che non c'è è un modo di
      consumare la batteria di qualcuno mentre gli si dice «sto pensando».
      Si dice cosa è successo e si lascia a lei la mossa.
    */
    if (!open.current) return;
    waiting.current = false;
    turn.current += 1;
    session.current?.cancel();
    session.current = null;
    setStuck(true);
    fire({ type: 'done' });
  }, []);

  const retry = useCallback(() => {
    const words = lastSaid.current.trim();
    if (!open.current || !words) return;
    setStuck(false);
    waiting.current = true;
    fire({ type: 'sent' });
    void Promise.resolve(opts.speak(words));
  }, [opts]);

  const openLive = useCallback(() => {
    // L'unico momento in cui iOS lascia sbloccare la voce è dentro il tocco
    // che apre: da qui in poi ORA può parlare senza che nessuno la tocchi.
    unlockSpeaking();
    open.current = true;
    waiting.current = false;
    setOn(true);
    setMuted(false);
    setStuck(false);
    setReadable(false);
    mutedRef.current = false;
    startListening();
  }, [startListening]);

  const closeLive = useCallback(() => {
    open.current = false;
    waiting.current = false;
    turn.current += 1;
    session.current?.cancel();
    session.current = null;
    voice.stop();
    setOn(false);
    setStuck(false);
    setReadable(false);
    fire({ type: 'done' });
  }, [voice]);

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    turn.current += 1;
    if (next) {
      session.current?.cancel();
      session.current = null;
      voice.stop();
      fire({ type: 'done' });
    } else {
      startListening();
    }
  }, [startListening, voice]);

  const interrupt = useCallback(() => {
    // Chi tocca mentre ORA parla vuole parlare, non zittirla e basta. E se
    // l'audio era ancora in preparazione, quello che arriva dopo non deve
    // mettersi a suonare da solo mezzo secondo più tardi.
    turn.current += 1;
    voice.stop();
    session.current?.cancel();
    session.current = null;
    waiting.current = false;
    setReadable(false);
    fire({ type: 'quiet' });
    startListening();
  }, [startListening, voice]);

  return {
    state,
    on,
    says: saying(state, muted, stuck),
    hint: hinting(state, muted, stuck, readable),
    heard: state.interim || state.said,
    muted,
    canRetry: stuck && Boolean(lastSaid.current),
    open: openLive,
    close: closeLive,
    toggleMute,
    interrupt,
    retry,
    answered,
    stumbled,
    marks: marks.current,
  };
}

/** La strada verso il server, presa una volta sola e non da qui. */
async function defaultRequest(path: string, init?: any): Promise<Response> {
  const { rawRequest } = await import('@/src/api/client');
  return rawRequest(path, init);
}
