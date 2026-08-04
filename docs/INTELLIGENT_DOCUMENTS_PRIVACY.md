# ORA — Intelligent documents privacy

- Isolamento per `user_id` su documenti, analisi, calendar drafts, ask.
- Nessun contenuto documentale nei log di errore (solo tipizzazione/`doc_id`).
- API key LLM letta solo dal backend; mai inviata al frontend; mai loggata; mai committata.
- Testo inviato a LLM solo se `DOCUMENT_AI_ENABLED=1`, provider configurato e preferenza `document_ai_analysis` non false.
- Controlli costo: max chars, max chunks, timeout, retry limitato, dedupe per `content_hash`.
- Pagine/testi vuoti o duplicati non inviati al modello (chunker).
- Documenti medici: nessuna diagnosi/terapia; priorità = scadenza/appuntamento.
- Cancellazione analisi: `DELETE /documents/{id}/analysis` mantiene il file.
- Hard delete documento rimuove blob (comportamento esistente).
- Path traversal bloccato su filename (basename).
- OCR: buffer in-memory; nessun temp file persistito dalla pipeline.
- Fixture di verifica: solo documenti sintetici non personali.
