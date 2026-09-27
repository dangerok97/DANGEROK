import assert from 'node:assert/strict';
import { test, beforeEach, afterEach } from 'node:test';
import { premiumVoice, oraVoice, systemVoice, speechChunks, italianVoice, pcmPlayer, streamingVoice } from './output.ts';
import { listen } from './speech.ts';

const flush = async () => { for (let i = 0; i < 24; i++) await Promise.resolve(); };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
};
const played: FakeAudio[] = [];
const synthesized: string[] = [];
let autoEnd = false;
let autoStart = true;
class FakeAudio {
  src = ''; volume = 1; paused = false;
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play() {
    played.push(this);
    if (autoStart) queueMicrotask(() => { this.onplaying?.(); if (autoEnd) this.onended?.(); });
    return Promise.resolve();
  }
  pause() { this.paused = true; }
}
class Utterance {
  text: string;
  constructor(text: string) { this.text = text; }
  onstart?: () => void; onend?: () => void;
}
let recognizer: FakeRecognition;
class FakeRecognition {
  onresult?: (e: any) => void; onend?: () => void; onerror?: (e: any) => void;
  onspeechend?: () => void; onspeechstart?: () => void;
  stopped = 0; aborted = 0;
  constructor() { recognizer = this; }
  start() {}
  stop() { this.stopped++; }
  abort() { this.aborted++; this.onerror?.({ error: 'aborted' }); }
}
const saved = { window: (globalThis as any).window, Audio: (globalThis as any).Audio, SpeechSynthesisUtterance: (globalThis as any).SpeechSynthesisUtterance };
beforeEach(() => {
  played.length = 0; synthesized.length = 0; autoEnd = false; autoStart = true;
  Object.assign(globalThis, { Audio: FakeAudio, SpeechSynthesisUtterance: Utterance, window: {
    SpeechRecognition: FakeRecognition,
    speechSynthesis: {
      cancel() {}, getVoices: () => [{ name: 'Alice', lang: 'it-IT' }, { name: 'Luca', lang: 'it-IT' }],
      speak(u: Utterance) { synthesized.push(u.text); queueMicrotask(() => { u.onstart?.(); u.onend?.(); }); },
    },
  } });
});
afterEach(() => Object.assign(globalThis, saved));
const audioResponse = () => ({ status: 200, ok: true, blob: async () => new Blob(['audio'], { type: 'audio/wav' }) } as Response);

const pcmNodes: any[] = [];
class PcmContext {
  state = 'running'; currentTime = 0; destination = {};
  resume() { return Promise.resolve(); }
  createBuffer(_channels: number, length: number, rate: number) {
    const data = new Float32Array(length);
    return { duration: length / rate, getChannelData: () => data };
  }
  createBufferSource() {
    const node = { buffer: null as any, at: 0, stopped: false, onended: null as any,
      start(at: number) { this.at = at; }, stop() { this.stopped = true; }, connect() {}, disconnect() {} };
    pcmNodes.push(node); return node;
  }
}
const packet = (bytes = [0, 64]) => JSON.stringify({ type: 'audio', data: btoa(String.fromCharCode(...bytes)), sample_rate: 24000, encoding: 'pcm_s16le' }) + '\n';
const donePacket = JSON.stringify({ type: 'done' }) + '\n';
function streamResponse() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(c) { controller = c; } });
  return { response: new Response(body, { headers: { 'Content-Type': 'application/x-ndjson' } }),
    send: (s: string) => controller.enqueue(new TextEncoder().encode(s)), close: () => controller.close() };
}
function enablePcm() { pcmNodes.length = 0; (globalThis as any).window.AudioContext = PcmContext; }

test('PCM handles odd network boundaries and schedules continuous signed samples', async () => {
  pcmNodes.length = 0;
  const player = pcmPlayer(new PcmContext() as any);
  player.push(new Uint8Array([0, 64, 0]));
  player.push(new Uint8Array([128]));
  assert.equal(pcmNodes[0].buffer.getChannelData(0)[0], .5);
  assert.equal(pcmNodes[1].buffer.getChannelData(0)[0], -1);
  assert.equal(pcmNodes[1].at, pcmNodes[0].at + pcmNodes[0].buffer.duration);
  let finished = false;
  const drained = player.finish().then(() => { finished = true; });
  await flush(); assert.equal(finished, false);
  pcmNodes[0].onended(); pcmNodes[1].onended();
  await drained; player.stop();
});

test('stream starts audio before response ends and avoids the availability round trip', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  enablePcm();
  const stream = streamResponse(); const paths: string[] = [];
  const voice = oraVoice(async path => { paths.push(path); return stream.response; }, { progressive: true, systemFallback: false });
  let starts = 0; let finished = false;
  const speaking = voice.speak('Sono qui.', { onStart: () => starts++ }).then(() => { finished = true; });
  await flush();
  const audio = packet(); stream.send(audio.slice(0, 12)); stream.send(audio.slice(12));
  await flush(); t.mock.timers.tick(61);
  assert.equal(starts, 1); assert.equal(finished, false);
  assert.deepEqual(paths, ['/voice/stream']);
  assert.equal(pcmNodes.length, 1);
  stream.send(donePacket); stream.close(); await flush();
  assert.equal(finished, false);
  pcmNodes[0].onended(); await speaking;
});

test('interrupt aborts the download, stops queued PCM and settles the reply', async () => {
  enablePcm(); const stream = streamResponse(); let signal: AbortSignal | undefined;
  const voice = streamingVoice(async (_path, init) => { signal = init.signal; return stream.response; });
  const speaking = voice.speak('Sono qui.');
  await flush(); stream.send(packet()); await flush();
  voice.stop(); await speaking;
  assert.equal(signal?.aborted, true);
  assert.equal(pcmNodes[0].stopped, true);
  assert.deepEqual(synthesized, []);
});

test('partial stream failure never repeats a spoken prefix with buffered synthesis', async () => {
  enablePcm(); const stream = streamResponse(); const paths: string[] = [];
  const voice = oraVoice(async path => { paths.push(path); return stream.response; }, { progressive: true, systemFallback: false });
  const rejected = assert.rejects(voice.speak('Sono qui.'), /speech_interrupted/);
  await flush(); stream.send(packet() + JSON.stringify({ type: 'error' }) + '\n');
  await rejected;
  assert.deepEqual(paths, ['/voice/stream']);
  assert.equal(pcmNodes[0].stopped, true);
});

test('EOF without the completion marker is a failure, not a completed reply', async () => {
  enablePcm(); const stream = streamResponse();
  const voice = streamingVoice(async () => stream.response);
  const rejected = assert.rejects(voice.speak('Sono qui.'));
  await flush(); stream.send(packet()); stream.close(); await rejected;
  assert.equal(pcmNodes[0].stopped, true);
});

test('stream failure before audio can recover through natural buffered synthesis', async () => {
  enablePcm(); autoEnd = true; const paths: string[] = [];
  const voice = oraVoice(async path => {
    paths.push(path);
    if (path.endsWith('stream')) return new Response(null, { status: 503 });
    if (path.endsWith('available')) return Response.json({ premium: true });
    return audioResponse();
  }, { progressive: true, systemFallback: false });
  await voice.speak('Sono qui.');
  assert.deepEqual(paths, ['/voice/stream', '/voice/available', '/voice/say']);
  assert.equal(played.length, 1); assert.deepEqual(synthesized, []);
});

test('a slow failed stream does not stack another synthesis delay', async t => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'] });
  enablePcm(); const stream = streamResponse(); const paths: string[] = [];
  const voice = oraVoice(async path => { paths.push(path); return stream.response; }, { progressive: true, systemFallback: false });
  const rejected = assert.rejects(voice.speak('Sono qui.'), /natural_voice_unavailable/);
  await flush(); t.mock.timers.tick(5000);
  stream.send(JSON.stringify({ type: 'error' }) + '\n');
  await rejected;
  assert.deepEqual(paths, ['/voice/stream']); assert.deepEqual(synthesized, []);
});

test('long answers preserve every word and have a short first phrase', () => {
  const text = 'Ho controllato il calendario e ho trovato tre impegni importanti. ' + 'Il prossimo appuntamento è domani alle dieci. '.repeat(45);
  const chunks = speechChunks(text);
  assert.ok(chunks.length > 3);
  assert.ok(chunks[0].length <= 220);
  assert.ok(chunks.every(c => c.length <= 480));
  assert.equal(chunks.join(' '), text.trim());
});

test('stop during download prevents late audio', async () => {
  const response = deferred<Response>();
  let signal: AbortSignal | undefined;
  const voice = premiumVoice(async (_path, init) => { signal = init.signal; return response.promise; });
  const speaking = voice.speak('Ciao.');
  voice.stop();
  assert.equal(signal?.aborted, true);
  response.resolve(audioResponse());
  await speaking;
  assert.equal(played.length, 0);
});

test('stop during playback settles even when browser never emits ended', async () => {
  const voice = premiumVoice(async () => audioResponse());
  let starts = 0;
  const speaking = voice.speak('Ciao.', { onStart: () => starts++ });
  await flush();
  assert.equal(starts, 1);
  voice.stop();
  await speaking;
  assert.ok(played[0].paused);
});

test('close during availability check cannot trigger system fallback', async () => {
  const response = deferred<Response>();
  const voice = oraVoice(async () => response.promise);
  const speaking = voice.speak('Questa risposta è ormai vecchia.');
  voice.stop();
  response.resolve(Response.json({ premium: false }));
  await speaking;
  assert.deepEqual(synthesized, []);
  assert.deepEqual(played, []);
});

test('next phrase is prepared while current audio plays, never played twice', async () => {
  let requests = 0; let starts = 0;
  const voice = premiumVoice(async () => { requests++; return audioResponse(); });
  const text = 'Ho controllato il calendario e ho trovato tre impegni importanti. ' + 'Ecco il dettaglio. '.repeat(30);
  const chunks = speechChunks(text);
  const speaking = voice.speak(text, { onStart: () => starts++ });
  await flush();
  assert.equal(played.length, 1);
  assert.equal(requests, 2);
  for (let i = 0; i < chunks.length; i++) { played.at(-1)?.onended?.(); await flush(); }
  await speaking;
  assert.equal(played.length, chunks.length);
  assert.equal(starts, 1);
});

test('failure of a later phrase reads only the remaining words', async () => {
  autoEnd = true;
  const text = 'Ho controllato il calendario e ho trovato tre impegni importanti. ' + 'Ecco il dettaglio. '.repeat(30);
  let requests = 0;
  const voice = oraVoice(async path => path.endsWith('available') ? Response.json({ premium: true }) : ++requests === 1 ? audioResponse() : new Response(null, { status: 204 }));
  await voice.speak(text);
  assert.equal(played.length, 1);
  assert.deepEqual(synthesized, [speechChunks(text).slice(1).join(' ')]);
});

test('audio that never starts times out and yields to system voice', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  autoStart = false;
  const voice = oraVoice(async path => path.endsWith('available') ? Response.json({ premium: true }) : audioResponse());
  const speaking = voice.speak('Ci sono.');
  await flush();
  t.mock.timers.tick(6001);
  await speaking;
  assert.deepEqual(synthesized, ['Ci sono.']);
  assert.ok(played[0].paused);
});

test('premium fetch timeout aborts the request and does not hang', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const voice = premiumVoice(async (_path, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new Error('aborted')));
  }));
  const result = assert.rejects(voice.speak('Ciao.'));
  t.mock.timers.tick(13501);
  await result;
});

test('natural conversation reports unavailable audio without substituting the browser voice', async () => {
  for (const available of [false, true]) {
    const voice = oraVoice(async path => path.endsWith('available') ? Response.json({ premium: available }) : new Response(null, { status: 204 }), { systemFallback: false });
    await assert.rejects(voice.speak('La risposta rimane in chat.'), /natural_voice_unavailable/);
    assert.equal(await voice.isAvailable(), false);
  }
  assert.deepEqual(synthesized, []);
});

test('a late successful neural response is not aborted at the former browser deadline', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  autoEnd = true;
  const reply = deferred<Response>();
  let signal: AbortSignal | undefined;
  const voice = premiumVoice(async (_path, init) => { signal = init.signal; return reply.promise; });
  const speaking = voice.speak('Sono qui.');
  t.mock.timers.tick(10820);
  assert.equal(signal?.aborted, false);
  reply.resolve(audioResponse());
  await speaking;
  assert.equal(played.length, 1);
});

test('availability recovers after a transient failure instead of caching forever', async t => {
  t.mock.timers.enable({ apis: ['Date'] });
  let tries = 0;
  const voice = premiumVoice(async () => {
    if (++tries === 1) throw new Error('offline');
    return Response.json({ premium: true });
  });
  assert.equal(await voice.isAvailable(), false);
  t.mock.timers.tick(5001);
  assert.equal(await voice.isAvailable(), true);
});

test('system voice prefers a masculine Italian stock voice and rejects unavailable output', async () => {
  assert.equal(italianVoice()?.name, 'Luca');
  (globalThis as any).window = {};
  await assert.rejects(systemVoice().speak('Ciao.'));
});

function heardResult(text: string, final: boolean) {
  return { resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: final })] };
}
test('recognition revisions do not duplicate words, and the end watchdog finishes once', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const heard: string[] = []; const trouble: string[] = [];
  listen({ onHearing() {}, onHeard: s => heard.push(s), onTrouble: s => trouble.push(s) });
  recognizer.onresult?.(heardResult('Mi senti', true));
  recognizer.onresult?.(heardResult('Mi senti bene', true));
  recognizer.onspeechend?.();
  t.mock.timers.tick(700);
  assert.equal(recognizer.stopped, 1);
  t.mock.timers.tick(800);
  recognizer.onend?.();
  assert.deepEqual(heard, ['Mi senti bene']);
  assert.deepEqual(trouble, []);
});

test('recognition cancellation suppresses late transcript and error callbacks', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const events: string[] = [];
  const listening = listen({ onHearing() {}, onHeard: s => events.push(s), onTrouble: s => events.push(s) });
  recognizer.onresult?.(heardResult('Messaggio vecchio', false));
  listening?.cancel();
  recognizer.onend?.();
  t.mock.timers.tick(20000);
  assert.deepEqual(events, []);
});

test('a new speech onset during the pause keeps listening', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const listening = listen({ onHearing() {}, onHeard() {}, onTrouble() {} });
  recognizer.onresult?.(heardResult('Vorrei', true));
  recognizer.onspeechend?.();
  t.mock.timers.tick(500);
  recognizer.onspeechstart?.();
  t.mock.timers.tick(500);
  assert.equal(recognizer.stopped, 0);
  listening?.cancel();
});
