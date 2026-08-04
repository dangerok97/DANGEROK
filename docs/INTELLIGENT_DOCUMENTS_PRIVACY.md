# ORA — Intelligent documents privacy

- Isolamento per `user_id` su documenti, analisi, calendar drafts.
- Nessun contenuto documentale nei log di errore (solo codici/id).
- Testo inviato a LLM solo se `DOCUMENT_AI_ENABLED=1`, provider configurato e preferenza utente `document_ai_analysis` non false.
- Preferenza utente: `users.preferences.document_ai_analysis` (default true).
- Documenti medici: nessuna diagnosi/terapia; priorità = scadenza/appuntamento, non gravità clinica.
- Cancellazione analisi: `DELETE /documents/{id}/analysis` mantiene il file.
- Hard delete documento rimuove blob (comportamento esistente).
- Path traversal bloccato su filename (basename).
- File temporanei worker: nessuno (in-memory queue).
