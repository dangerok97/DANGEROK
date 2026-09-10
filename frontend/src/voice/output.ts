/**
 * Chi dà voce a una risposta, e perché la conversazione non deve saperlo.
 *
 *     LA VOCE DI SISTEMA È LA RETE, NON LA VOCE DI ORA.
 *
 * `speechSynthesis` legge l'italiano e si sente che lo sta leggendo:
 * scandisce, non respira, mette l'accento dove capita. Come rete di sicurezza
 * è perfetta — c'è sempre, non costa niente, funziona senza rete — e come voce
 * di ORA no.
 *
 * Quindi qui c'è un contratto e non un fornitore. `SpeechOutputProvider` dice
 * soltanto: sai dire questa frase, sai smettere, e adesso puoi. Sotto ci sono
 * due implementazioni; sopra non c'è niente che sappia quale delle due sta
 * parlando. Il giorno che ne arriva una migliore si aggiunge qui.
 */

export type SpeechOutputProvider = {
  /** Come si chiama, per chi guarda cosa sta succedendo. Mai sullo schermo. */
  readonly name: string;
  /** Se in questo momento può parlare. */
  isAvailable: () => Promise<boolean> | boolean;
  /** Dice la frase. Risolve quando ha finito di dirla. */
  speak: (text: string, hooks?: SpeakHooks) => Promise<void>;
  /** Zitta, subito. */
  stop: () => void;
};

export type SpeakHooks = {
  /** Ha cominciato: è il momento in cui una persona sente la prima parola. */
  onStart?: () => void;
};

/** Dove il server tiene la voce. Il resto dell'app non lo sa. */
const SAY = '/voice/say';
const AVAILABLE = '/voice/available';

// ---------------------------------------------------------------------------

/**
 * La voce buona: nasce sul server, arriva come suono, non resta da nessuna
 * parte.
 *
 * Un 204 non è un errore: vuol dire che là dietro non c'era nessuno e che
 * tocca alla rete. Lo stesso vale per una rete lenta o per un file che il
 * browser non sa suonare — in tutti e tre i casi la frase viene detta lo
 * stesso, con l'altra voce, e nessuno vede un messaggio d'errore.
 */
export function premiumVoice(
  request: (path: string, init?: any) => Promise<Response>,
): SpeechOutputProvider {
  let playing: HTMLAudioElement | null = null;
  let known: boolean | null = null;

  return {
    name: 'premium',
    async isAvailable() {
      if (typeof window === 'undefined' || typeof Audio === 'undefined') return false;
      if (known !== null) return known;
      try {
        const answer = await request(AVAILABLE);
        const body = await answer.json();
        known = Boolean(body?.premium);
      } catch {
        known = false;
      }
      return known;
    },
    async speak(text, hooks) {
      const answer = await request(SAY, {
        method: 'POST',
        body: JSON.stringify({ text, language: 'it' }),
      });
      if (answer.status === 204) throw new Error('no_premium_voice');
      if (!answer.ok) throw new Error(`voice_${answer.status}`);
      const sound = await answer.blob();
      const url = URL.createObjectURL(sound);
      const audio = new Audio(url);
      playing = audio;
      try {
        await new Promise<void>((done, fail) => {
          audio.onplaying = () => hooks?.onStart?.();
          audio.onended = () => done();
          audio.onerror = () => fail(new Error('audio_failed'));
          void audio.play().catch(fail);
        });
      } finally {
        playing = null;
        URL.revokeObjectURL(url);
      }
    },
    stop() {
      try {
        playing?.pause();
      } catch {
        /* già ferma */
      }
      playing = null;
    },
  };
}

/**
 * La voce del browser. Sempre lì, e si sente che è una macchina.
 *
 * iOS non lascia parlare nessuno che non sia stato toccato: la prima
 * pronuncia deve partire dentro un gesto della persona, e la risposta di ORA
 * arriva secondi dopo. Per questo `unlock()` esiste e viene chiamato al
 * tocco — dice una cosa vuota a volume zero e da lì in poi la voce è libera.
 */
export function systemVoice(): SpeechOutputProvider {
  return {
    name: 'system',
    isAvailable: () => typeof window !== 'undefined' && 'speechSynthesis' in window,
    speak(text, hooks) {
      return new Promise<void>((done) => {
        if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
          done();
          return;
        }
        try {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.lang = 'it-IT';
          utterance.rate = 0.98;
          utterance.pitch = 1.0;
          const voice = italianVoice();
          if (voice) utterance.voice = voice;
          utterance.onstart = () => hooks?.onStart?.();
          utterance.onend = () => done();
          utterance.onerror = () => done();
          window.speechSynthesis.speak(utterance);
        } catch {
          done();
        }
      });
    },
    stop() {
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* niente da fermare */
      }
    },
  };
}

/** La voce italiana che suona meno da robot fra quelle che ci sono. */
export function italianVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
  let voices: SpeechSynthesisVoice[] = [];
  try {
    voices = window.speechSynthesis.getVoices() || [];
  } catch {
    return null;
  }
  const italian = voices.filter((v) => (v.lang || '').toLowerCase().startsWith('it'));
  if (!italian.length) return null;
  const preferred = ['alice', 'federica', 'luca', 'siri'];
  for (const name of preferred) {
    const found = italian.find((v) => (v.name || '').toLowerCase().includes(name));
    if (found) return found;
  }
  return italian[0];
}

/**
 * La voce di ORA: la migliore che c'è adesso, e se non c'è, quella che c'è.
 *
 * Chi chiama non sa quale delle due ha parlato e non deve saperlo. Quello che
 * sa è che la frase è stata detta — o, nel caso peggiore in cui non parli
 * nessuno, che è comunque scritta sullo schermo, perché è sempre la stessa.
 */
export function oraVoice(
  request: (path: string, init?: any) => Promise<Response>,
): SpeechOutputProvider {
  const premium = premiumVoice(request);
  const system = systemVoice();
  let spokenBy: SpeechOutputProvider | null = null;

  return {
    name: 'ora',
    isAvailable: () => true,
    async speak(text, hooks) {
      if (await premium.isAvailable()) {
        try {
          spokenBy = premium;
          await premium.speak(text, hooks);
          return;
        } catch {
          // La voce buona non ce l'ha fatta. Non è una cosa da dire a
          // nessuno: si parla lo stesso, con l'altra.
        }
      }
      spokenBy = system;
      await system.speak(text, hooks);
    },
    stop() {
      premium.stop();
      system.stop();
      spokenBy = null;
    },
  };
}

/**
 * iOS: il permesso di parlare si prende una volta, dentro un tocco.
 *
 * È un trucco, e sta scritto che è un trucco. Senza, Safari resta muto per
 * tutta la sessione e nessuno capisce perché.
 */
export function unlockSpeaking(): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
  try {
    const silence = new SpeechSynthesisUtterance('');
    silence.volume = 0;
    window.speechSynthesis.speak(silence);
  } catch {
    /* se non si sblocca, si legge */
  }
}
