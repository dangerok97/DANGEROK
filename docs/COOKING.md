# ORA Cucina — ricettario privato, fase 1 (22 ottobre 2026)

## Flusso

Da VITA, Cucina e ricette apre /cucina. L'utente incolla un link HTTPS o il
testo di una ricetta. POST /api/recipes/preview propone una bozza e
non salva nulla. Un pulsante di conferma esplicito salva la bozza corretta.

Per testi con sezioni Ingredienti e Procedimento il parser copia soltanto
le righe effettivamente fornite, senza stimare quantità. I link social
vengono salvati come fonti ma NON viene letto il video né ricostruita
la ricetta dal solo URL. Mancanza di ingredienti o passaggi = Da completare.

Funzioni: archivio persistente privato, ricerca per titolo/ingredienti/tag,
preferiti, già cucinate, modifica con revisione e cancellazione confermata.
Importare la stessa fonte non crea duplicati.

## API

POST /api/recipes/preview: {source} -> {draft, quality, warnings}
GET /api/recipes/items -> {items}
POST /api/recipes/items: RecipeWrite revision 0 -> {item, created}
PUT /api/recipes/items/{id}: RecipeWrite revision N -> {item}
DELETE /api/recipes/items/{id}?revision=N -> {deleted}

Tutte le API richiedono l'autenticazione ORA; ogni record Mongo in
ora_recipes contiene user_id e una chiave deterministica owner + fonte.
Aggiornamento e cancellazione richiedono la revisione in corso (CAS).
Limite 250 ricette per utente, nessuna nuova dipendenza o migrazione distruttiva.

## Limiti espliciti della fase 1

Non ancora presenti: OCR fotografie, audio/video extraction, Share Extension
iOS già installata, modalità cucina guidata, lista della spesa, planning,
nutrizione e tool conversazionali/WhatsApp per lettura e scrittura.

Test richiesti prima di dichiarare la pubblicazione:
cd backend && pytest -n 0 recipes/tests/test_parser.py recipes/tests/test_service.py
cd frontend && npx tsc --noEmit
cd frontend && npx expo export --platform web

Serve anche collaudo live con account sintetico e lettura dello stato Railway.
Non interpretare un commit come prova del deploy.
