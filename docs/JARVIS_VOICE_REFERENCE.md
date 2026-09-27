## Aggiornamento 27 settembre 2026 — Nuovo obiettivo concordato

L'utente sceglie una voce originale quanto più naturale e vicina al carattere
richiesto, con ironia discreta. Non si cerca più una replica identica dell'attore.
La nuova base in-app è Algieba; direzione morbida, tono composto, frasi legate.
Audio progressivo tramite gemini-3.1-flash-tts-preview e Web Audio; nessuna
voce personalizzata o registrazione dell'attore caricata. Verifiche cloud e
limiti aggiornati in RESUME_2026_09_27.md.

# JARVIS — riferimento vocale per ORA

Ricerca del 27 settembre 2026. Richiesta: voce identica al JARVIS di Iron Man,
in una conversazione italiana naturale. Il requisito di identità **non è
soddisfatto** dalla voce stock attualmente configurata. Non chiamare un preset
generico «la voce originale» e non dedurre la somiglianza dal successo dell'API.

## Riscontri dalle fonti aperte

1. **Identità italiana verificata.** Il pressbook di *Iron Man 2*, edizione
   italiana, pagina 39, attribuisce JARVIS a **Nino D'Agata**. La scheda di
   Antonio Genna conferma lo stesso doppiatore per Iron Man 1–3 e Avengers.
   Paul Bettany è il riferimento della versione inglese; imitare il suo accento
   inglese non ricrea automaticamente la voce che l'utente ricorda in italiano.
   Fonti: [pressbook](https://pad.mymovies.it/filmclub/2008/12/128/mymovies.pdf),
   [scheda del doppiatore](https://www.antoniogenna.net/doppiaggio/voci/vocinda.htm).

2. **Una performance recitata.** Nell'intervista diretta a SuperHeroHype del
   16 maggio 2008, Bettany racconta di aver registrato le battute in cabina con
   Jon Favreau. È prova del processo di interpretazione, non delle impostazioni
   di un sintetizzatore. Nessuna frequenza fondamentale o ricetta DSP di JARVIS
   è pubblicata in quell'intervista.
   [Intervista](https://www.superherohype.com/features/96605-paul-bettany-on-voicing-iron-mans-jarvis).

3. **Attenzione all'attribuzione degli effetti.** L'intervista a Christopher
   Boyes in AudioTechnology descrive l'uso misurato di pitch e risonanza per
   Tony Stark e di effetti più marcati per Iron Monger. Non specifica la catena
   di JARVIS. Non trasferire quelle impostazioni alla voce italiana come se
   fossero una ricetta documentata. L'indicazione utile alla progettazione è
   preservare l'intelligibilità e la componente umana.
   [Intervista tecnica, pag. 3](https://www.audiotechnology.com/PDF/FEATURES/AT61_SOUND_FOR_IRON_MAN.pdf).

4. **Campioni: provenienza prima delle misure.** La scheda di Nino D'Agata
   offre un MP3 pubblico di circa 25,94 s, stereo 44,1 kHz, verificato nei suoi
   metadati. La pagina dichiara esplicitamente che proviene da *Castle*, dove
   doppia David Andrews: è escluso come campione della performance JARVIS.
   La clip italiana del salvataggio aereo di *Iron Man 3* è documentata come
   distribuita da Disney il 4 maggio 2013. In questa sessione non è stato
   ottenuto un campione isolato e verificato del suo dialogo: niente misure
   inventate di Hz, formanti, parole/minuto o percentuali di somiglianza.
   [Provenienza della clip](https://www.badtaste.it/articoli/iron-man-3-ecco-il-salvataggio-aereo-i-produttori-spiegano-com-stato-fatto).

## Traduzione in requisiti di ORA

Queste sono **scelte di direzione da validare all'ascolto**, non misurazioni
della traccia cinematografica. La somiglianza richiede più del solo tono basso.

| Dimensione | Direzione per ORA | Verifica necessaria |
| --- | --- | --- |
| Identità e timbro | Maschile adulto, medio-basso, composto; niente voce da annunciatore | Confronto con battute italiane attribuite a JARVIS |
| Prosodia | Frasi collegate, accenti sulle informazioni utili, finali naturali | Domande, conferme, numeri, nomi e risposte lunghe |
| Ritmo | Pause funzionali al senso; niente sillabe scandite uniformemente | Prova con lo stesso testo e senza cambiare velocità di playback |
| Ironia | Una breve osservazione asciutta quando appropriata | Il testo deve contenere la battuta; la sintesi non inventa parole |
| Presenza | Calma operativa anche quando corregge un errore | Nessuna enfasi teatrale, nessuna battuta su identità o conferme delicate |
| Trattamento | Voce intelligibile prima di qualsiasi colorazione elettronica | Confronto in cuffia e su altoparlante mobile |

L'identità dipende dalla voce specifica; la prosodia dall'interpretazione; il
carattere anche da cosa ORA dice. Si valutano separatamente. Modificare pitch,
rate o aggiungere un filtro metallico a una voce standard non dimostra identità.

## Opzioni reali e limite attuale

Gemini documenta voci stock, progettazione da descrizione e replica con campione
e registrazione di consenso. Nel catalogo consultato Charon è descritto come
«Informative», Algieba come «Smooth»: le etichette non sono prove di somiglianza
con Nino D'Agata. Non è stato individuato un modello ufficiale italiano JARVIS
integrabile con disponibilità e condizioni verificate. Questo è l'esito della
ricerca svolta, non una prova che nessun modello esista.

[Catalogo e TTS](https://ai.google.dev/gemini-api/docs/speech-generation)
· [Requisiti della replica](https://ai.google.dev/gemini-api/docs/voice-replication).

Per puntare all'identità serve un modello vocale dedicato, con materiale
utilizzabile e disponibilità API verificate, seguito da ascolti comparativi
sulle stesse frasi. Non basta caricare una scena pubblica nel servizio: il
flusso di replica consultato richiede anche una registrazione di consenso
dello stesso parlante. Non sono state caricate registrazioni dell'attore presso
servizi di clonazione né creati profili vocali. Non è stato aggiunto un provider
fittizio o una dipendenza non utilizzabile.

## Integrazione e diagnosi concreta

Il punto di integrazione esiste già: `backend/voice/providers.py`, contratto
`SpeechOutputProvider` e risultato `Spoken`. Un futuro modello verificato
sostituirà la sintesi mantenendo chat, strumenti, memoria e autorizzazioni.

Le prove cloud hanno evidenziato anche un problema distinto dalla fedeltà:
OpenAI ha risposto 429; la prima credenziale Gemini 402; la seconda ha generato
WAV con successo. Un campione sintetico breve ha richiesto 10,82 s complessivi
dalla chiamata HTTP, contro un timeout del client di 10,5 s. Sono singole
osservazioni, non mediane né una misura dell'intero turno vocale.

Correzione: cooldown per singola credenziale, limite client di 13,5 s con
margine sul budget server, nessuna sostituzione automatica con la voce del
browser nel dialogo live. Se l'audio naturale manca, il testo resta visibile,
compare l'indicazione già presente e ORA torna ad ascoltare. L'attesa massima
non è una pausa imposta alle risposte veloci. Nessuna modifica a chiamate reali,
contatti o configurazione Railway.

Restano da verificare: somiglianza percettiva con il riferimento italiano,
tempo al primo audio su più turni, interruzione su dispositivi reali e streaming
audio effettivo. Il playback anticipa la frase successiva, ma non è streaming
del primo audio durante la generazione e non offre barge-in vocale automatico.
