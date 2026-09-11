/**
 * V3.13 Sprint 1 — la voce come modo di entrare, non come secondo assistente.
 *
 * Run: node --experimental-strip-types src/voice/voice313.test.ts
 *
 * Due famiglie di prove. La prima è sul nucleo puro: come si legge una
 * risposta ad alta voce e come si passa da uno stato all'altro quando la
 * persona interrompe, tace o nega il microfono — cose che si possono
 * sbagliare senza che nessuno se ne accorga finché non capitano dal vivo.
 *
 * La seconda è la parte che conta di più e non si vede: che la voce non abbia
 * cominciato a essere un'altra ORA. Un secondo agente, un secondo posto dove
 * si tengono le conversazioni, una memoria che esiste solo se hai parlato, un
 * elenco di comandi riconosciuti a parole — sono tutte cose che si aggiungono
 * un pezzo per volta, ognuna con una buona ragione, e alla fine la stessa
 * persona ha due assistenti che non si conoscono.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  VOICE_START,
  forSpeaking,
  nextVoice,
  hinting,
  inParole,
  pronounceable,
  saying,
  spansOf,
  voiceSays,
  type VoicePhase,
  type VoiceState,
} from './speech.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

const SPEECH = 'src/voice/speech.ts';
const HOOK = 'src/voice/useVoice.ts';
const SCREEN = 'src/components/ora/OraConversationScreen.tsx';
const COMPOSER = 'src/components/ora/OraComposer.tsx';
const LIVE = 'src/voice/useLiveVoice.ts';
const LIVE_SCREEN = 'src/voice/LiveVoiceScreen.tsx';
const OUTPUT = 'src/voice/output.ts';

const tests: Array<[string, () => void]> = [];
const test = (name: string, fn: () => void) => tests.push([name, fn]);

// ---------------------------------------------------------------------------
// Detto invece che letto
// ---------------------------------------------------------------------------

test('§11 la voce dice le stesse parole che si leggono, senza la pagina', () => {
  const written =
    '**Ho controllato** il calendario:\n' +
    '- la partenza è alle 06:00\n' +
    '- la vacanza dura tutto il giorno\n\n' +
    'Vedi [il dettaglio](https://esempio.it/x) quando vuoi.';
  const said = forSpeaking(written);

  // Nessun segno che esiste solo sullo schermo.
  for (const mark of ['**', '- ', '](', 'http']) {
    assert.ok(!said.includes(mark), `la voce legge la composizione: ${mark}`);
  }
  // E nessuna informazione in meno: quello che si sente dice quello che si
  // legge. Non le stesse lettere — «06:00» detto carattere per carattere non
  // è italiano — ma la stessa ora, e tutte le parole che c'erano.
  for (const word of ['calendario', 'partenza', 'vacanza', 'dettaglio']) {
    assert.ok(said.includes(word), `la voce ha perso «${word}»`);
  }
  assert.ok(said.includes('alle sei'), `l'ora non è arrivata alla voce: ${said}`);
});

test('una risposta vuota non fa parlare nessuno', () => {
  assert.equal(forSpeaking(''), '');
  assert.equal(forSpeaking('   \n  '), '');
  assert.equal(forSpeaking('**   **'), '');
});

// ---------------------------------------------------------------------------
// Gli stati di una conversazione parlata
// ---------------------------------------------------------------------------

const after = (events: Parameters<typeof nextVoice>[1][]): VoiceState =>
  events.reduce(nextVoice, VOICE_START);

test('§3 tocco, ascolto, parole: e mentre parla si vede che parla', () => {
  const heard = after([
    { type: 'ask' },
    { type: 'allowed' },
    { type: 'hearing', words: 'quando parto per' },
  ]);
  assert.equal(heard.phase, 'listening');
  assert.equal(heard.interim, 'quando parto per');
  assert.equal(voiceSays(heard), 'Ti ascolto');

  const done = nextVoice(heard, { type: 'heard', words: 'quando parto per Vibo?' });
  assert.equal(done.phase, 'heard');
  assert.equal(done.said, 'quando parto per Vibo?');
  assert.equal(done.interim, '', 'la trascrizione provvisoria resta sullo schermo');
});

test('§14 silenzio: non è un errore, e non chiude niente', () => {
  const quiet = after([
    { type: 'ask' },
    { type: 'allowed' },
    { type: 'heard', words: '   ' },
  ]);
  assert.equal(quiet.phase, 'idle');
  assert.equal(quiet.trouble, 'heard_nothing');
  assert.ok(voiceSays(quiet)?.includes('Non ho sentito'));
});

test('§14 microfono negato: si può ancora scrivere, e lo dice', () => {
  const denied = after([{ type: 'ask' }, { type: 'trouble', why: 'no_permission' }]);
  assert.equal(denied.phase, 'blocked');
  const says = voiceSays(denied) || '';
  assert.ok(says.includes('scrivermi') || says.includes('scrivi'), says);
});

test('§7 chi tocca il microfono mentre ORA parla vuole parlare, non zittirla', () => {
  const speaking = after([
    { type: 'ask' },
    { type: 'allowed' },
    { type: 'heard', words: 'cosa devo fare oggi?' },
    { type: 'sent' },
    { type: 'answered' },
    { type: 'speaking' },
  ]);
  assert.equal(speaking.phase, 'speaking');
  const interrupted = nextVoice(speaking, { type: 'quiet' });
  assert.equal(interrupted.phase, 'idle');
  assert.equal(interrupted.trouble, null, 'interrompere non è un guaio');
});

test('§8 il tempo si misura tutto, e non decide niente', () => {
  const spans = spansOf({
    mic: 1_000,
    end_of_speech: 2_600,
    transcript: 2_700,
    asked: 2_720,
    answer: 4_900,
    speech: 5_050,
  });
  const named = Object.fromEntries(spans.map((s) => [s.what, s.ms]));
  assert.equal(named['ascolto'], 1600);
  assert.equal(named['trascrizione'], 100);
  assert.equal(named['ragionamento'], 2180);
  assert.equal(named['totale'], 4050);
  // Un giro a metà si misura per quello che ha fatto, senza inventare il resto.
  assert.equal(spansOf({ mic: 10 }).length, 0);
});

// ---------------------------------------------------------------------------
// Nessun secondo assistente
// ---------------------------------------------------------------------------

test('§17 la voce non parla con il server: consegna parole a chi già ci parla', () => {
  const code = readCode(SPEECH) + readCode(HOOK);
  for (const forbidden of ['aiCoreStart', 'aiCoreMessage', 'fetch(', "api.", '/conversation']) {
    assert.ok(
      !code.includes(forbidden),
      `la voce si è costruita una sua strada verso il server: ${forbidden}`,
    );
  }
});

test('§17 nessuna memoria che esiste solo perché hai parlato', () => {
  const code = readCode(SPEECH) + readCode(HOOK);
  for (const forbidden of ['localStorage', 'AsyncStorage', 'sessionStorage', 'IndexedDB']) {
    assert.ok(!code.includes(forbidden), `la voce si tiene qualcosa per sé: ${forbidden}`);
  }
});

test('§17 nessun comando riconosciuto a parole', () => {
  const code = (readCode(SPEECH) + readCode(HOOK)).toLowerCase();
  for (const word of [
    'calendario',
    'promemoria',
    'dentista',
    'mutuo',
    'appuntamento',
    'ricordami',
    'aggiungi',
  ]) {
    assert.ok(
      !code.includes(`'${word}`) && !code.includes(`"${word}`),
      `la voce ha imparato un comando: ${word}`,
    );
  }
});

test('§4 quello che si dice e quello che si scrive passano dalla stessa porta', () => {
  const screen = readCode(SCREEN);
  assert.ok(screen.includes('useVoice('), 'la voce non è collegata alla conversazione');
  assert.ok(
    /speak:\s*\(words\)\s*=>\s*\{[\s\S]{0,200}sendWords\(words\)/.test(screen),
    'la voce non manda le parole dalla stessa funzione del testo',
  );
  assert.ok(
    /const sendWords[\s\S]{0,900}dispatch\(clientMessageId/.test(screen),
    'le parole dette non finiscono nella conversazione',
  );
  // Una sola sessione, una sola conversazione: nessun `sessionId` parallelo.
  const voiceCode = readCode(SPEECH) + readCode(HOOK);
  assert.ok(!voiceCode.includes('sessionId'), 'la voce tiene una sua sessione');
});

test('§16 la provenienza cambia, il comportamento no', () => {
  const screen = readCode(SCREEN);
  assert.ok(
    /origin:\s*startedByVoice\.current[\s\S]{0,80}'voice'/.test(screen),
    'una conversazione cominciata parlando non lo dice',
  );
  // E non esiste nessun ramo che tratti diversamente quello che è stato detto.
  assert.ok(
    !/if\s*\(\s*startedByVoice\.current\s*\)\s*\{[\s\S]{0,400}(memor|govern|authorit)/i.test(screen),
    'la voce cambia come si ricorda o cosa si può fare',
  );
});

test('§11 il campo mostra quello che sta sentendo, e resta lo stesso campo', () => {
  const composer = readCode(COMPOSER);
  assert.ok(
    /const shown = listening && interim \? interim : value;/.test(composer),
    'la trascrizione non compare dove si scrive',
  );
  assert.ok(composer.includes('-voice-hint'), 'non c’è dove leggere «Ti ascolto»');
  // La dettatura resta nel composer: non apre niente.
  assert.ok(
    !/Modal|overlay/i.test(composer),
    'dettare una frase apre una schermata',
  );
});

// ---------------------------------------------------------------------------
// Due modi, non due assistenti
// ---------------------------------------------------------------------------

test('§2 + §3 il microfono detta, l’onda conversa: due controlli distinti', () => {
  const composer = readCode(COMPOSER);
  assert.ok(composer.includes('-mic'), 'manca il microfono');
  assert.ok(composer.includes('-voice-mode'), 'manca il controllo della voce');
  // Icone diverse: un microfono e delle barre d'audio si distinguono senza
  // leggere niente, ed è la prova che deve passare — nessuno legge un
  // tutorial prima di parlare.
  assert.ok(/name=\{listening \? 'mic' : 'mic-outline'\}/.test(composer),
    'il microfono non è un microfono');
  // Non un glifo preso a caso: quattro barre disuguali, che si leggono come
  // suono. Tre cursori uguali sarebbero le impostazioni.
  assert.ok(/<VoiceWave tint=/.test(composer), 'la modalità vocale non ha un’onda');
  assert.ok(/\[9, 17, 13, 7\]/.test(composer), 'le barre sono tutte uguali: sembra un equalizzatore');
  assert.ok(!/options-outline|pulse-outline/.test(composer),
    'è tornata un’icona che vuol dire un’altra cosa');
  // E le etichette dicono cose diverse, per chi non vede le icone.
  assert.ok(/Detta un messaggio/.test(composer));
  assert.ok(/Parla con ORA a voce/.test(composer));
});

test('§2 dettare non fa parlare ORA', () => {
  const dictation = readCode(HOOK);
  // Da `output` prende una cosa sola, e non è una voce: `unlockSpeaking`
  // serve perché iOS vuole il permesso di parlare dentro un tocco, e quel
  // tocco spesso è questo.
  const takes = /import \{([^}]*)\} from '\.\/output'/.exec(dictation)?.[1] || '';
  assert.equal(takes.trim(), 'unlockSpeaking');
  const calls = dictation.replace(/opts\.speak\(said\)/g, '');
  assert.ok(
    !/\.speak\(|answered\(/.test(calls),
    'il microfono legge la risposta ad alta voce: quella è l’altra modalità',
  );
});

test('§4 la modalità vocale usa la stessa conversazione, non una sua', () => {
  const live = readCode(LIVE);
  for (const forbidden of ['aiCoreStart', 'aiCoreMessage', 'sessionId', 'localStorage']) {
    assert.ok(!live.includes(forbidden), `la modalità vocale si è messa in proprio: ${forbidden}`);
  }
  assert.ok(/opts\.speak\(said\)/.test(live), 'non manda le parole a chi già parla con ORA');
  const screen = readCode(SCREEN);
  assert.ok(
    /useLiveVoice\(\{[\s\S]{0,200}sendWords\(words\)/.test(screen),
    'la modalità vocale non passa dalla porta del testo',
  );
});

test('§5 il giro riparte da solo: parla, pensa, risponde, riascolta', () => {
  const live = readCode(LIVE);
  // Dopo aver parlato torna ad ascoltare, e lo fa quando l’audio è finito.
  assert.ok(/\.finally\([\s\S]{0,220}startListening\(\)/.test(live),
    'dopo la risposta non riapre l’ascolto');
  // Il silenzio non chiude la conversazione.
  assert.ok(/if \(!said\) \{[\s\S]{0,120}startListening\(\)/.test(live));
});

test('§7 tap-to-interrupt: mentre parla, un tocco la ferma e riapre l’ascolto', () => {
  const live = readCode(LIVE);
  assert.ok(
    /const interrupt = useCallback\([\s\S]{0,320}voice\.stop\(\)[\s\S]{0,320}startListening\(\)/.test(live),
    'interrompere non riapre l’ascolto',
  );
  const screenFile = readCode(LIVE_SCREEN);
  assert.ok(/onPress=\{speaking \|\| preparing \? live\.interrupt : undefined\}/.test(screenFile),
    'toccare mentre l’audio si prepara non la ferma');
});

test('§6 uscire non porta via niente', () => {
  const live = readCode(LIVE);
  assert.ok(/const closeLive = useCallback/.test(live));
  // Chiudere ferma il microfono e la voce, e non tocca i turni: non li ha.
  assert.ok(!/setTurns|turns/.test(live), 'la modalità vocale tiene una sua copia dei turni');
  const screenFile = readCode(LIVE_SCREEN);
  for (const control of ['live-voice-close', 'live-voice-mute', 'live-voice-keyboard']) {
    assert.ok(screenFile.includes(control), `manca il controllo ${control}`);
  }
});

test('§5 + §12 stati in italiano, nessuna etichetta tecnica', () => {
  // Le parole degli stati stanno con gli stati: è la parte pura, e si prova
  // una per una senza microfono e senza browser.
  for (const human of [
    'Ti ascolto',
    'Sto pensando',
    'Sto per rispondere',
    'ORA sta parlando',
    'Microfono in pausa',
  ]) {
    assert.ok(readCode(SPEECH).includes(human), `manca lo stato «${human}»`);
  }
  const shown = readCode(SPEECH) + readCode(LIVE) + readCode(LIVE_SCREEN);
  for (const jargon of ['STT', 'TTS', 'recording', 'processing', 'transcribing']) {
    assert.ok(!shown.includes(jargon), `sullo schermo compare «${jargon}»`);
  }
});

// ---------------------------------------------------------------------------
// Chi parla, e chi parla quando quello non può
// ---------------------------------------------------------------------------

test('§10 la conversazione non sa di chi sia la voce', () => {
  const out = readCode(OUTPUT);
  assert.ok(/export function oraVoice/.test(out));
  for (const method of ['speak', 'stop', 'isAvailable']) {
    assert.ok(out.includes(`${method}`), `il contratto non ha ${method}`);
  }
  // Nessun nome di fornitore fuori da qui.
  const elsewhere = readCode(LIVE) + readCode(HOOK) + readCode(SCREEN) + readCode(LIVE_SCREEN);
  for (const vendor of ['gemini', 'openai', 'elevenlabs', 'azure', 'polly']) {
    assert.ok(
      !elsewhere.toLowerCase().includes(vendor),
      `il nome di un fornitore è arrivato fin dentro l’app: ${vendor}`,
    );
  }
});

test('§11 se la voce buona non c’è, parla quella di sistema', () => {
  const out = readCode(OUTPUT);
  assert.ok(
    /if \(await premium\.isAvailable\(\)\) \{[\s\S]{0,400}catch \{[\s\S]{0,200}\}[\s\S]{0,120}system\.speak/.test(out),
    'un fallimento della voce premium non passa a quella di sistema',
  );
  // Un 204 non è un errore da mostrare: vuol dire «parla tu».
  assert.ok(/answer\.status === 204/.test(out));
  // E fermarsi ferma tutte e due.
  assert.ok(/stop\(\) \{[\s\S]{0,120}premium\.stop\(\);[\s\S]{0,80}system\.stop\(\);/.test(out));
});

test('§9 la voce non riscrive la risposta, la dice', () => {
  const live = readCode(LIVE);
  // Passa da `forSpeaking`, che toglie la composizione e non tocca le parole.
  assert.ok(/forSpeaking\(text\)/.test(live));
  assert.ok(!/summar|riassum|shorten|slice\(0, \d+\)/.test(live), 'la voce accorcia la risposta');
});

test('§18 la voce non può scavalcare l’autorità', () => {
  const everything = readCode(LIVE) + readCode(HOOK) + readCode(OUTPUT) + readCode(SPEECH);
  for (const forbidden of ['authority', 'consent', 'approve', 'user_authority', 'grant']) {
    assert.ok(
      !everything.toLowerCase().includes(forbidden),
      `la voce tocca l’autorità: ${forbidden}`,
    );
  }
});

test('§14 quando la voce non si può, si scrive: il campo non si chiude mai', () => {
  const composer = readCode(COMPOSER);
  assert.ok(
    /editable=\{!busy && !disabled && !listening\}/.test(composer),
    'il campo di testo dipende dalla voce più di quanto dovrebbe',
  );
  // Il microfono resta toccabile mentre sta ascoltando: è così che si dice
  // «ho finito» senza aspettare il silenzio. Interrompere ORA mentre parla è
  // un'altra cosa e vive nella schermata vocale, dove il composer non c'è.
  assert.ok(
    /disabled=\{\(busy && !listening\) \|\| disabled\}/.test(composer),
    'mentre detta non si può chiudere la dettatura',
  );
});

// ---------------------------------------------------------------------------
// Il posto dove si scrive
// ---------------------------------------------------------------------------

test('§1 il campo prende tutta la larghezza, i comandi stanno sotto', () => {
  const composer = readCode(COMPOSER);
  // Un contenitore solo, con dentro il campo e poi la riga dei comandi.
  assert.ok(/styles\.shell\b/.test(composer), 'non c’è un contenitore unico');
  assert.ok(/width: '100%'/.test(composer), 'il campo divide lo spazio con i pulsanti');
  const field = composer.indexOf('-input');
  const controls = composer.indexOf('styles.controls');
  assert.ok(field > 0 && controls > field, 'i comandi stanno ancora accanto al campo');
  // Allegare a sinistra, parlare e mandare a destra.
  const attach = composer.indexOf('-attach');
  const spacer = composer.indexOf('styles.gap');
  const send = composer.indexOf('-send');
  assert.ok(attach < spacer && spacer < send, 'l’ordine dei comandi non è quello');
});

test('§1 il campo cresce con quello che ci si scrive, entro un limite', () => {
  const composer = readCode(COMPOSER);
  assert.ok(/onContentSizeChange/.test(composer), 'il campo non cresce');
  assert.ok(/Math\.min\(Math\.max\(grown, \d+\), \d+\)/.test(composer),
    'il campo cresce senza limite, o non cresce affatto');
});

test('§1 le etichette dicono cosa fanno, e i bersagli si toccano', () => {
  const composer = readCode(COMPOSER);
  for (const label of [
    // Il «+» non allega piu' un documento: chiede cosa aggiungere, e
    // apre il selettore giusto dopo. L'etichetta deve dire quello che
    // succede quando lo si tocca, non quello che succedeva prima.
    'Aggiungi foto, file o documenti',
    'Detta un messaggio',
    'Parla con ORA a voce',
    'Invia messaggio',
  ]) {
    assert.ok(composer.includes(label), `manca l’etichetta «${label}»`);
  }
  // Quarantaquattro punti, presi dai token e non scritti a mano.
  assert.ok(/width: tokens\.touch\.min/.test(composer));
  assert.ok(/height: tokens\.touch\.min/.test(composer));
});

// ---------------------------------------------------------------------------
// Gli stati che una persona legge, e quando li legge
// ---------------------------------------------------------------------------

const at = (phase: VoicePhase): VoiceState => ({ ...VOICE_START, phase });

test('§2 «ORA sta parlando» solo quando si sente davvero', () => {
  assert.equal(saying(at('speaking'), false, false), 'ORA sta parlando');
  // Mentre l'audio si prepara la voce non è ancora partita: dirlo sarebbe
  // una promessa che a volte non si mantiene, e chi la sente resta a fissare
  // uno schermo muto.
  assert.equal(saying(at('preparing'), false, false), 'Sto per rispondere');
  assert.equal(saying(at('thinking'), false, false), 'Sto pensando');
  assert.equal(saying(at('listening'), false, false), 'Ti ascolto');
  for (const phase of ['idle', 'asking', 'thinking', 'preparing', 'blocked'] as VoicePhase[]) {
    assert.ok(
      !saying(at(phase), false, false).includes('sta parlando'),
      `«sta parlando» compare in ${phase}`,
    );
  }
});

test('§2 pausa del microfono ed errore hanno uno stato loro', () => {
  assert.equal(saying(at('listening'), true, false), 'Microfono in pausa');
  assert.equal(saying(at('thinking'), false, true), 'Non è arrivata risposta');
  // E l'errore vince sulla pausa: è la cosa che blocca.
  assert.equal(saying(at('listening'), true, true), 'Non è arrivata risposta');
});

test('§4 l’errore della risposta e quello della sola voce sono due cose', () => {
  // La risposta non è arrivata: si può riprovare, o chiudere e scrivere.
  const stuck = hinting(at('idle'), false, true, false) || '';
  assert.ok(stuck.includes('riprovare'), stuck);

  // La risposta c'è ma non si riesce a dirla: resta leggibile, e lo si dice.
  const mute = hinting(at('listening'), false, false, true) || '';
  assert.ok(mute.includes('scritta'), mute);
  assert.ok(!mute.includes('riprovare'), 'la risposta c’è: non c’è niente da riprovare');

  // Nessun nome di fornitore e nessun dettaglio di fatturazione, mai.
  for (const words of [stuck, mute]) {
    for (const leak of ['gemini', 'openai', 'credit', 'quota', '429', 'api']) {
      assert.ok(!words.toLowerCase().includes(leak), `l’interfaccia dice «${leak}»`);
    }
  }
});

test('§4 in ascolto, senza guai, non c’è niente da leggere', () => {
  assert.equal(hinting(at('listening'), false, false, false), null);
  assert.equal(hinting(at('idle'), false, false, false), null);
});

// ---------------------------------------------------------------------------
// Chi torna dal passato non tocca il presente
// ---------------------------------------------------------------------------

test('§3 ogni giro ha il suo numero, e le risposte in ritardo cadono', () => {
  const live = readCode(LIVE);
  // Un solo posto dove si decide se una risposta è ancora attuale.
  assert.ok(
    /const current = useCallback\(\s*\(mine: number\) =>[\s\S]{0,120}turn\.current === mine/.test(live),
    'non c’è modo di riconoscere una risposta in ritardo',
  );
  // Ogni callback del riconoscitore lo controlla.
  for (const hook of ['onHearing', 'onEndOfSpeech', 'onHeard', 'onTrouble']) {
    const at_ = live.indexOf(hook);
    assert.ok(at_ > 0, `manca ${hook}`);
    assert.ok(
      /current\(mine\)/.test(live.slice(at_, at_ + 220)),
      `${hook} agisce anche quando è in ritardo`,
    );
  }
  // E l'audio pure: né l'inizio né la fine possono riaprire un giro chiuso.
  assert.ok(/onStart: \(\) => \{[\s\S]{0,400}if \(!current\(mine\)\) return;/.test(live));
  assert.ok(/\.finally\(\(\) => \{\s*if \(!current\(mine\)\) return;/.test(live));
});

test('§3 chiudere, mettere in pausa e interrompere invecchiano quello che c’era', () => {
  const live = readCode(LIVE);
  for (const action of ['closeLive', 'toggleMute', 'interrupt']) {
    const from = live.indexOf(`const ${action} = useCallback`);
    assert.ok(from > 0, `manca ${action}`);
    const body = live.slice(from, from + 700);
    assert.ok(/turn\.current \+= 1/.test(body), `${action} non invalida il giro`);
    assert.ok(/voice\.stop\(\)|session\.current\?\.cancel\(\)/.test(body),
      `${action} non ferma niente`);
  }
  // Chiudere ferma tutte e due le cose che possono continuare da sole.
  const closing = live.slice(live.indexOf('const closeLive'), live.indexOf('const toggleMute'));
  assert.ok(/session\.current\?\.cancel\(\)/.test(closing) && /voice\.stop\(\)/.test(closing));
});

test('§4 se la risposta non arriva non si ritenta all’infinito', () => {
  const live = readCode(LIVE);
  const from = live.indexOf('const stumbled = useCallback');
  const body = live.slice(from, from + 600);
  assert.ok(/setStuck\(true\)/.test(body), 'non lo dice a nessuno');
  assert.ok(!/startListening\(\)/.test(body), 'riparte da solo davanti a un servizio che non c’è');
  // Ma la persona può chiedere di riprovare, e riprova quello che aveva detto.
  assert.ok(/const retry = useCallback/.test(live));
  assert.ok(/lastSaid\.current/.test(live));
});

// ---------------------------------------------------------------------------
// Il movimento, per chi ne ha chiesto di meno
// ---------------------------------------------------------------------------

test('§2 chi ha chiesto meno movimento non trova niente che pulsa', () => {
  const screenFile = readCode(LIVE_SCREEN);
  assert.ok(/prefers-reduced-motion/.test(screenFile), 'la preferenza non viene letta');
  assert.ok(/isReduceMotionEnabled/.test(screenFile), 'su dispositivo non viene letta');
  assert.ok(
    /if \(!live\.on \|\| calm\) \{[\s\S]{0,80}setValue\(0\)/.test(screenFile),
    'la preferenza viene letta e ignorata',
  );
});

test('§2 il testo sta fuori dall’elemento che si muove', () => {
  const screenFile = readCode(LIVE_SCREEN);
  const orb = screenFile.indexOf('testID="live-voice-orb"');
  const state = screenFile.indexOf('testID="live-voice-state"');
  assert.ok(orb > 0 && state > orb, 'lo stato è dentro l’elemento animato');
  // Il segno centrale è contenuto, non un disco grande con dentro le parole.
  const mark = /mark: \{ width: (\d+)/.exec(screenFile);
  assert.ok(mark && Number(mark[1]) <= 56, `l’elemento centrale è ancora grande: ${mark?.[1]}`);
});

// ---------------------------------------------------------------------------
// Scritta per essere letta, detta per essere capita
// ---------------------------------------------------------------------------

test('§5 una data e un\u2019ora si dicono come le direbbe qualcuno', () => {
  assert.equal(
    pronounceable('Il 20/09 alle 06:00 parti per Vibo.'),
    'Il venti settembre alle sei parti per Vibo.',
  );
  assert.equal(
    pronounceable('Venerdì 12/09/2026 alle 19:00 devi chiamare il notaio.'),
    'Venerdì dodici settembre duemilaventisei alle diciannove devi chiamare il notaio.',
  );
  assert.equal(
    pronounceable('La visita è alle 10:30.'),
    'La visita è alle dieci e mezza.',
  );
});

test('§5 una cifra si dice, e la frase tiene la sua punteggiatura', () => {
  assert.equal(
    pronounceable('Ho visto una spesa di 4.000 € per il notaio.'),
    'Ho visto una spesa di quattromila euro per il notaio.',
  );
  // Il punto finale non fa parte della cifra: mangiarselo toglie alla voce
  // la pausa che quella frase aveva.
  assert.ok(pronounceable('Stipendio: €2.050.').endsWith('euro.'));
  assert.ok(pronounceable('Sono 12,50 euro.').includes('dodici euro e cinquanta'));
});

test('§5 non si aggiunge e non si toglie niente', () => {
  // Un codice resta un codice: detto a parole non lo riconoscerebbe nessuno.
  const treno = pronounceable('Treno Intercity 555, posto 15A, PNR VPKY35.');
  assert.ok(treno.includes('15A') && treno.includes('VPKY35'));
  // Un anno resta un anno.
  assert.ok(pronounceable('Nel 2026 si vedrà.').includes('2026'));
  // Un indirizzo web non si sillaba, ma la frase non perde il fatto che c\u2019era.
  assert.equal(
    pronounceable('Trovi il dettaglio su https://esempio.it/x quando vuoi.'),
    'Trovi il dettaglio su un link quando vuoi.',
  );
  // Una frase senza niente da trasformare torna identica.
  const piana = 'Per domani non vedo impegni urgenti.';
  assert.equal(pronounceable(piana), piana);
});

test('§5 i numeri in parole, dove si sbaglia di solito', () => {
  assert.equal(inParole(21), 'ventuno');
  assert.equal(inParole(28), 'ventotto');
  assert.equal(inParole(100), 'cento');
  assert.equal(inParole(1000), 'mille');
  assert.equal(inParole(2050), 'duemilacinquanta');
  assert.equal(inParole(4000), 'quattromila');
  // Oltre non si prova nemmeno: sbagliare una cifra è peggio che lasciarla.
  assert.equal(inParole(1_000_000), null);
  assert.equal(inParole(-3), null);
  assert.equal(inParole(1.5), null);
});

test('§5 la voce passa dalla forma pronunciabile, e il testo no', () => {
  // `forSpeaking` è l\u2019unico imbuto: quello che si legge non cambia.
  const spoken = forSpeaking('**Il 20/09 alle 06:00** parti.');
  assert.ok(spoken.includes('venti settembre'), spoken);
  assert.ok(!spoken.includes('**'), spoken);
  const speech = readCode(SPEECH);
  assert.ok(/return pronounceable\(out\.trim\(\)\)/.test(speech),
    'la forma pronunciabile non è nell\u2019unico posto da cui passa la voce');
  // E nessuno la applica al testo che finisce sullo schermo.
  const screen = readCode(SCREEN);
  assert.ok(!/pronounceable/.test(screen), 'la conversazione scritta viene riscritta');
});

// ---------------------------------------------------------------------------

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (e: any) {
    failed += 1;
    console.log(`  NO  ${name}`);
    console.log(`      ${e.message}`);
  }
}
console.log(`\n${tests.length - failed}/${tests.length} passati`);
if (failed) process.exit(1);