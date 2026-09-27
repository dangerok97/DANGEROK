/** Audio delivery only. Conversation, memory and authority stay in AI Core. */
export type SpeechOutputProvider = {
  readonly name: string;
  isAvailable: () => Promise<boolean> | boolean;
  speak: (text: string, hooks?: SpeakHooks) => Promise<void>;
  stop: () => void;
};
export type SpeakHooks = { onStart?: () => void };
const SAY = '/voice/say';
const AVAILABLE = '/voice/available';
const aborted = () => new Error('voice_cancelled');

/** Short first breath; complete text, split only at a sentence or word boundary. */
export function speechChunks(text: string): string[] {
  let rest = text.trim();
  const chunks: string[] = [];
  while (rest) {
    const limit = chunks.length ? 480 : 220;
    if (rest.length <= limit) { chunks.push(rest); break; }
    const prefix = rest.slice(0, limit + 1);
    const stops = [...prefix.matchAll(/[.!?;:]\s+/g)].filter(m => (m.index || 0) >= 45);
    const stop = stops.at(-1);
    const cut = stop ? stop.index! + 1 : prefix.lastIndexOf(' ');
    // An indivisible token is kept whole; the server accepts up to 4000 chars.
    const boundary = cut > 0 ? cut : (rest.indexOf(' ') > 0 ? rest.indexOf(' ') : rest.length);
    chunks.push(rest.slice(0, boundary));
    rest = rest.slice(boundary).trim();
  }
  return chunks;
}

class SpeechFailure extends Error {
  remaining: string;
  constructor(remaining: string) { super('audio_failed'); this.remaining = remaining; }
}
let unlockedAudio: HTMLAudioElement | null = null;

export function premiumVoice(request: (path: string, init?: any) => Promise<Response>): SpeechOutputProvider {
  let epoch = 0;
  let playing: HTMLAudioElement | null = null;
  let releasePlayback: (() => void) | null = null;
  const pending = new Set<AbortController>();
  let known: { value: boolean; until: number } | null = null;

  const stop = () => {
    epoch += 1;
    for (const controller of pending) controller.abort();
    pending.clear();
    playing?.pause();
    releasePlayback?.();
    releasePlayback = null;
    playing = null;
  };
  async function load(text: string, mine: number): Promise<Blob> {
    if (mine !== epoch) throw aborted();
    const controller = new AbortController();
    pending.add(controller);
    // Leave headroom for authentication and transfer around the 9 s server budget.
    const timer = setTimeout(() => controller.abort(), 13500);
    try {
      const answer = await request(SAY, {
        method: 'POST', signal: controller.signal,
        body: JSON.stringify({ text, language: 'it' }),
      });
      if (mine !== epoch || controller.signal.aborted) throw aborted();
      if (answer.status === 204) {
        known = { value: false, until: Date.now() + 30000 };
        throw new Error('no_premium_voice');
      }
      if (!answer.ok) throw new Error(`voice_${answer.status}`);
      const sound = await answer.blob();
      if (mine !== epoch || controller.signal.aborted) throw aborted();
      return sound;
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
    }
  }
  return {
    name: 'premium',
    async isAvailable() {
      if (typeof window === 'undefined' || typeof Audio === 'undefined') return false;
      if (known && known.until > Date.now()) return known.value;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 2000);
      pending.add(controller);
      try {
        const answer = await request(AVAILABLE, { signal: controller.signal });
        const body = await answer.json();
        known = { value: answer.ok && Boolean(body?.premium), until: Date.now() + 30000 };
      } catch {
        known = { value: false, until: Date.now() + 5000 };
      } finally {
        clearTimeout(timer);
        pending.delete(controller);
      }
      return known.value;
    },
    async speak(text, hooks) {
      stop();
      const mine = epoch;
      const chunks = speechChunks(text);
      // Rejections are handled immediately, even while the previous chunk plays.
      const preload = (words: string) => load(words, mine).then(
        blob => ({ blob, error: null }), error => ({ blob: null, error }),
      );
      let next = chunks.length ? preload(chunks[0]) : null;
      let started = false;
      for (let i = 0; i < chunks.length; i += 1) {
        try {
          const result = await next!;
          if (mine !== epoch) return;
          if (result.error || !result.blob) throw result.error;
          next = i + 1 < chunks.length ? preload(chunks[i + 1]) : null;
          const url = URL.createObjectURL(result.blob);
          const audio = unlockedAudio || new Audio();
          playing = audio;
          audio.src = url;
          audio.volume = 1;
          try {
            await new Promise<void>((done, fail) => {
              let timer: ReturnType<typeof setTimeout>;
              let settled = false;
              const finish = (error?: Error) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                audio.onplaying = audio.onended = audio.onerror = null;
                if (releasePlayback === cancel) releasePlayback = null;
                if (error) fail(error); else done();
              };
              const cancel = () => finish();
              releasePlayback = cancel;
              timer = setTimeout(() => finish(new Error('audio_start_timeout')), 6000);
              audio.onplaying = () => {
                if (mine !== epoch) { audio.pause(); finish(); return; }
                clearTimeout(timer);
                timer = setTimeout(() => finish(new Error('audio_end_timeout')), Math.max(20000, chunks[i].length * 160));
                if (!started) { started = true; hooks?.onStart?.(); }
              };
              audio.onended = () => finish();
              audio.onerror = () => finish(new Error('audio_failed'));
              void audio.play().catch(error => finish(error));
            });
          } finally {
            audio.pause();
            if (playing === audio) playing = null;
            URL.revokeObjectURL(url);
          }
          if (mine !== epoch) return;
        } catch {
          if (mine !== epoch) return;
          stop();
          throw new SpeechFailure(chunks.slice(i).join(' '));
        }
      }
    },
    stop,
  };
}

export function systemVoice(): SpeechOutputProvider {
  let release: (() => void) | null = null;
  const stop = () => {
    release?.();
    release = null;
    try { window.speechSynthesis?.cancel(); } catch { /* already stopped */ }
  };
  return {
    name: 'system',
    isAvailable: () => typeof window !== 'undefined' && 'speechSynthesis' in window,
    speak(text, hooks) {
      stop();
      return new Promise<void>((done, fail) => {
        if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
          fail(new Error('no_speech_output')); return;
        }
        let timer: ReturnType<typeof setTimeout>;
        const finish = (error?: Error) => {
          clearTimeout(timer);
          if (release === cancel) release = null;
          utterance.onstart = utterance.onend = utterance.onerror = null;
          if (error) fail(error); else done();
        };
        const cancel = () => finish();
        const utterance = new SpeechSynthesisUtterance(text);
        release = cancel;
        utterance.lang = 'it-IT';
        utterance.rate = 1.02;
        utterance.pitch = 0.95;
        const voice = italianVoice();
        if (voice) utterance.voice = voice;
        timer = setTimeout(() => { finish(new Error('speech_start_timeout')); window.speechSynthesis.cancel(); }, 6000);
        utterance.onstart = () => {
          clearTimeout(timer);
          timer = setTimeout(() => { finish(new Error('speech_end_timeout')); window.speechSynthesis.cancel(); }, Math.max(20000, text.length * 180));
          hooks?.onStart?.();
        };
        utterance.onend = () => finish();
        utterance.onerror = () => finish(new Error('speech_failed'));
        try { window.speechSynthesis.speak(utterance); } catch { finish(new Error('speech_failed')); }
      });
    },
    stop,
  };
}

export function italianVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
  let voices: SpeechSynthesisVoice[];
  try { voices = window.speechSynthesis.getVoices() || []; } catch { return null; }
  const italian = voices.filter(v => (v.lang || '').toLowerCase().startsWith('it'));
  for (const name of ['luca', 'cosimo', 'diego', 'elsa', 'alice', 'federica']) {
    const found = italian.find(v => (v.name || '').toLowerCase().includes(name));
    if (found) return found;
  }
  return italian[0] || null;
}

export function oraVoice(
  request: (path: string, init?: any) => Promise<Response>,
  options: { systemFallback?: boolean } = {},
): SpeechOutputProvider {
  const premium = premiumVoice(request);
  const system = systemVoice();
  const allowSystem = options.systemFallback !== false;
  let epoch = 0;
  return {
    name: 'ora',
    isAvailable: async () => (await premium.isAvailable()) || (allowSystem && system.isAvailable()),
    async speak(text, hooks) {
      const mine = ++epoch;
      premium.stop(); system.stop();
      let remaining = text;
      let started = false;
      const once: SpeakHooks = { onStart: () => {
        if (mine !== epoch || started) return;
        started = true; hooks?.onStart?.();
      } };
      if (await premium.isAvailable()) {
        if (mine !== epoch) return;
        try { await premium.speak(text, once); return; }
        catch (error) { if (error instanceof SpeechFailure) remaining = error.remaining; }
      }
      if (mine !== epoch) return;
      if (!allowSystem) throw new Error('natural_voice_unavailable');
      await system.speak(remaining, once);
    },
    stop() { epoch += 1; premium.stop(); system.stop(); },
  };
}

/** Unlock both audio paths during the user's opening gesture (Safari). */
export function unlockSpeaking(): void {
  if (typeof window === 'undefined') return;
  try {
    if (typeof Audio !== 'undefined') {
      unlockedAudio ||= new Audio();
      const audio = unlockedAudio;
      audio.src = 'data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQIAAAAAAA==';
      audio.volume = 0;
      void audio.play().then(() => { audio.pause(); audio.volume = 1; }).catch(() => {});
    }
    if ('speechSynthesis' in window) {
      const silence = new SpeechSynthesisUtterance('');
      silence.volume = 0;
      window.speechSynthesis.speak(silence);
    }
  } catch { /* The written answer remains available. */ }
}
