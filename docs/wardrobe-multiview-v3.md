# ORA Guardaroba V3 — fronte e retro di un unico capo

## Release 1: multi-view reale e retro nell'analisi AI

**Compatibilità**
- I capi V1/V2 restano nei documenti Mongo già esistenti: campo
  photo_encrypted (front), revision, id, user_id, visual_profile.
- I nuovi documenti aggiungono soltanto photo_back_encrypted e
  front_source_encrypted/back_source_encrypted (tutti AES-GCM, AAD distinti).
  L'alias /photo legacy e il campo pubblico "photo" continuano a funzionare.
  La risposta aggiunge back_photo e has_back, senza un secondo garment ID.
- Per i nuovi upload vengono conservate due rappresentazioni della stessa
  fotografia: riferimento ottimizzato MAX 1200px (senza EXIF) cifrato e
  miniatura MAX 480px cifrata. Questo NON è il file originale a piena risoluzione.
  I capi già caricati hanno solo la versione esistente 480px; niente migrazione
  o inventata versione raw originale.
- L'utente può selezionare il fronte e il retro, salvandoli in sequenza
  con revisioni ottimistiche. Il retro è facoltativo, ma richiede un fronte.
  Se fallisce un upload, ORA informa quale vista manca e conserva quelle valide.
  DELETE retro è confermato e non elimina il capo o la foto fronte.

**API**
- POST /api/wardrobe/items/{id}/photo e /photo/front: stesso fronte
- POST /api/wardrobe/items/{id}/photo/back: salva seconda vista sul medesimo ID
- DELETE /api/wardrobe/items/{id}/photo/back: rimuove solo il retro
- POST /api/wardrobe/items/{id}/appearance/analyze?revision=N: usa un'immagine
  effimera in due riquadri etichettati FRONTE/RETRO, con una sola chiamata
  ORA Vision. Foto origini non passano al motore outfit.
- PUT /api/wardrobe/items/{id}/appearance: l'utente approva i campi,
  fra cui back_graphic (nessuna, piccola, grande, incerta) e back_style
  (nessuno, casual, streetwear, incerto).
- Cambiare entrambe le foto invalida il profilo approvato e le valutazioni
  pregresse dell'outfit. Conferma vincolata alla revisione del documento e alla
  firma SHA256 della/e vista/e effettivamente analizzate. Nessuna foto di
  account diversi può essere associata a un capo.

**Scelte prudenti del motore**
- La stampa retro può contare in una valutazione, ma una stampa piccola non
  reclassifica automaticamente il livello di formalità del capo.
- Solo attributi APPROVATI dall'utente arrivano allo stylist testuale.
- Warning esplicito se una grafica sul retro rilevante può contrastare con
  un contesto chic, senza fingere di aver visto il capo indossato.

## Release 2: "foto vetrina" (NON inclusa in questa PR)

Il cutout di qualità e-commerce richiede **segmentation/matting** vero, non
una semplice rimozione dei pixel quasi bianchi. Non introdurre ritagli che
mangiano parti di una camicia, lacci o bordi scuri su sfondi complessi.

Design previsto:
- Input: front/back source JPEG cifrati e privati, mai URL pubblici.
- Inference: modello con licenza dei PESI verificata anche per uso commerciale;
  isolamento del carico ONNX CPU, limiti memoria/tempo e niente logging immagini.
- Output: PNG trasparente cifrato per singola vista, conservato separatamente
  dalla foto di riferimento. Anteprima su scacchiera o sfondo neutro.
- User review: accetta / scarta / rigenera. Nessun overwrite dell'originale.
- Quality gate: segmentare capi bianchi su sfondi chiari, neri su sfondi scuri,
  frange, capelli nella foto, scarpe/lacci e superfici non uniformi senza
  cancellare il capo. Se il risultato non supera QA, mostrare l'immagine
  originale e dichiarare che lo scontorno non è disponibile.
- Non includere il modello BRIA RMBG 1.4/2.0 senza licenza commerciale e
  revisione del contratto; il software rembg MIT non implica automaticamente
  licenza analoga dei modelli ONNX usati. Verificare peso e provenienza prima
  di aggiungere nuove dipendenze o chiamate a terze parti.

## Test e rilascio
- I test sintetici verificano un solo item con due viste, isolamento utente,
  cifratura e chiavi AAD distinte, upload 5 MB, assenza metadata e file raw,
  hash combinato, invalidazione dopo modifica/rimozione del retro e advisory AI.
- Test browser reale sul form fronte/retro, conferma di visual profile,
  card catalogo e rimozione retro.
- GitHub CI totale verde prima del merge; Railway backend/web stesso SHA e
  /api/health + /healthz prima di considerare pubblicato.
- Qualità della classificazione su foto vere da validare con utente; eventuale
  HTTP 402 del provider AI rimane un limite quota non risolvibile dal formato
  dell'immagine.
