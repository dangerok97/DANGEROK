# ==========================================================
# ITERAZIONE 22 — Document Understanding Engine (generico, no LLM)
# ==========================================================
iter22_document_understanding_engine:
  status: DONE
  goal: |
    Trasformare Document Insights in un motore documentale generico,
    schema-driven, estendibile. NO LLM, NO AI generativa. Retrocompat
    100% con GET /api/documents/{id}/insights.
  new_modules:
    - documents/schema_registry.py    # registry con 13 schemi + register API
    - documents/document_classifier.py # multi-signal (keyword+label+filename+coherence)
    - documents/field_resolver.py      # label-aware, confidence-scored resolver
    - documents/person_detector.py     # blacklist role/label (no falsi Posto Unico…)
    - documents/technical_ids.py       # TktID/UUID/hash/barcode → categoria dedicata
  api_additions:
    - classification: {type_key,type_label,confidence,matched_rules,scores,thresholds}
    - schema_used:    {type_key,type_label,version,info_order}
    - resolved_fields[]:  field_key,label,value,confidence,source_snippet,source_page,resolver_rule
    - hidden_fields[]:    40..59 confidence (API-only, mai in UI)
    - technical_identifiers: {grouped:{labelled,uuids,hashes,long_numeric}, flat[]}
    - Iter21 keys (summary, entities, extraction, technical_metadata, history, content) PRESERVED
  thresholds_env:
    - DOCUMENT_INSIGHTS_CONFIDENCE_THRESHOLD=60  (visibile)
    - DOCUMENT_INSIGHTS_HIDDEN_LOWER_THRESHOLD=40
    - classification: ≥70 tipo specifico | 50-69 con coherence | <50 generic
  documents_supported: [ticket, invoice, receipt, contract, bill, medical,
                        certificate, id_card, passport, cv, bank_statement,
                        tax_doc, generic-fallback]
  anti_hallucination_verified:
    - Data ordine NON sostituisce Data evento (context bias)
    - Ora emissione NON sostituisce Apertura porte / Ora evento
    - TktID → technical_identifiers, MAI order_number né phones
    - Posto Unico / Tribuna / Platea NON diventano persone
    - 11 cifre senza label NON diventano P.IVA/CF
    - Stesso valore NON compare in due resolved_fields
    - Generic fallback su documento ambiguo
  ui_changes:
    - app/document/[id].tsx:
        Info → usa resolved_fields (fallback summary.fields se vuoto)
        Insights → dedica sezione "Identificativi tecnici" + nasconde valori
                   già promossi a resolved_fields (no duplicazione visiva)
        Etichette italiane: ENTITY_LABELS mappa order_ids→"Numeri di ordine",
                            technical_ids→"Identificativi tecnici" ecc.
    - src/api/client.ts: DocumentInsights + ResolvedField types aggiornati
  extensibility:
    - Nuovo tipo doc = register_document_type(DocumentSchema(...))
    - Zero modifiche al codice esistente. Test extensibility incluso.
  tests:
    - test_iter22_document_understanding.py: 26 test PASS
        * 10 classification (tutti i tipi + generic fallback)
        * 4 resolved_fields (ticket/invoice/contract/id_card)
        * 6 priority rules (anti-hallucination §8)
        * 2 confidence (thresholds + snippet length)
        * 2 retrocompat Iter21
        * 1 extensibility (registrazione live)
        * 1 unknown→generic
    - Regressione Iter19/20/21: 18+10+13 = 41 test PASS, 0 regressioni
    - Live smoke (testing_agent): 4/4 PASS su ingress pubblico
    - Report: /app/test_reports/iteration_18.json + junit XML
  screenshots:
    - /app/docs/screenshots/iter22_biglietto_info.jpg  (tab Info biglietto)
    - /app/docs/screenshots/iter22_biglietto_insights.jpg  (Identificativi tecnici)
    - /app/docs/screenshots/iter22_fattura_info.jpg    (tab Info fattura)
    - /app/docs/screenshots/iter22_contratto_info.jpg  (tab Info contratto)
  constraints_honored:
    - NO LLM, NO AI generativa
    - Decision Engine, Ranking, Explainability, Behavior, Memory,
      Upload, OCR, Storage: INVARIATI


# ==========================================================
# ITERAZIONE 21 (bug-fix) — Document Insights: reduce false positives
# ==========================================================
iter21_bugfix_false_positives:
  status: DONE
  problem: |
    L'estrazione deterministica classificava:
      - technical IDs (TktID / order / unix timestamp) come "phones"
      - sequenze 11-digit come "Codice Fiscale" (che è 16 alfanumerico)
      - token "biglietto CONCERTO" come order_id (label troppo debole)
  fix:
    - insights.py: nuova pipeline priority-based con span reservation.
    - Phones: label OBBLIGATORIA (tel/cell/mob/phone/fax/contatto/whatsapp) o
      prefisso intl `+XX` o formato IT mobile `3XX + 6-7 digits`. 7..15 cifre.
    - Codice Fiscale (persona): regex rigida 16-char italiana.
    - P.IVA / CF numerico: 11 cifre + label obbligatoria a distanza max 25 char
      non-digit non-newline (permette "P.IVA emittente: NNNNNNNNNNN").
    - Order/Ticket IDs: label obbligatoria; captured value deve contenere una
      cifra (rifiuta "CONCERTO" dopo "BIGLIETTO"); mai un token che sembra date/time.
    - `numbers` unifica order_ids + generic long IDs su span NON claimed
      (backward compat con test_i1).
    - build_structured_summary: ticket/invoice ora usano `order_ids[0]` prima
      del fallback `numbers[0]`.
  files_modified:
    - /app/backend/documents/insights.py
    - /app/backend/tests/test_iter21_document_insights.py (aggiunta classe
      TestInsightsFalsePositiveGuards con 5 nuovi test)
    - /app/frontend/app/(tabs)/documenti.tsx (cleanup: rimossi
      DetailSheet/MetaLine dead code e stili orfani sheetOverlay/sheet/
      sheetHead/sheetTitle/metaBlock/metaLine/metaKey/metaVal)
  tests:
    - 13 test iter21 passano (8 originali + 5 nuovi false-positive guards).
    - Live smoke sull'ingress pubblico: 4/4 pass (test_iter21_live_smoke.py).
    - Regressione totale documents: 41 test passano.
    - No LLM call sul path insights (test_i6 stable duration_ms).
  no_regressions:
    - test_i1_ticket_type_detected (order "1284925775" ancora in numbers)
    - test_i2_email_url_phone_extracted (email/url/phone tutti ok)
    - test_i7_invoice_type (invoice ancora rilevato, P.IVA in tax_ids)


# ==========================================================
# ITERAZIONE 20 — Document Intelligence (OCR & Text Extraction)
# ==========================================================
iter20:
  status: DONE
  scope: pipeline testo (PDF nativo + OCR + text/plain) — NO AI, NO summary, NO classifier, NO decisioni
  pipeline:
    - Upload → ExtractionPipeline → TextCleaner → LanguageDetector → persist(documents/life_graph/knowledge)
    - PDFTextProvider (astratto) → impl PyPDFProvider (pypdf 6.14.2). Motivo: puro Python, no wrapper C, robusto per PDF nativi con testo.
    - OCRProvider (astratto) → impl TesseractOCRProvider (pytesseract 0.3.13 + binario tesseract 5.3 con lingua ita+eng). Motivo: motore locale, offline, deterministico, gratuito, sostituibile.
    - TextFileProvider per text/plain, text/csv, text/markdown, text/rtf
    - Sostituibilità: PDFTextProvider/OCRProvider sono ABC — sostituire con Vision API, AWS Textract, ecc. senza cambiare service/router.
  files_created:
    - /app/backend/documents/extraction.py (pipeline + provider + cleaner + language detector)
    - /app/backend/tests/test_iter20_document_intelligence.py
  files_modified:
    - /app/backend/documents/service.py (upload triggerà _extract_and_persist; ricerca ora include extracted_text)
    - /app/backend/documents/context_provider.py (aggiunge excerpt, pages, language, ocr_used, text_extracted)
    - /app/backend/routers/memory.py (Memory Ask legge extracted_text con cap 2500 char/doc)
    - /app/backend/.env (DOCUMENT_OCR_ENABLED=true, DOCUMENT_EXTRACTION_ENABLED=true, DOCUMENT_CONTEXT_ENABLED=false, DOCUMENT_AI_ENABLED=false, DOCUMENT_OCR_LANGS="ita+eng")
    - /app/backend/requirements.txt (pypdf, pytesseract)
  db_schema_extensions_on_documents:
    - text_extracted (bool)
    - extracted_text (string, cap 500KB)
    - extraction_engine (string)
    - ocr_used (bool)
    - pages (int)
    - detected_language (string, "it"|"en"|null) — NB: rinominato da `language` per evitare conflitto MongoDB text-index override
    - confidence (float, OCR only)
    - extraction_error_code (string|null)
    - extraction_warnings (string[])
    - extraction_duration_ms (float)
    - extracted_at (iso)
  wiring:
    - Life Graph node type=document: attributes ora includono text_extracted, ocr_used, pages, language, confidence (aggiornato via life_graph.update_node)
    - Knowledge Layer: knowledge.merge chiamata con notes=extracted_text[:1000], source_type="document_extraction"
    - Memory Ask (POST /api/memory/ask): ora costruisce blocco "Documenti dell'utente" con excerpt di contenuto (fino a 2500 char/doc), permette domande su contenuto e numeri specifici (es. "numero fattura", "totale bolletta")
    - Search (GET /api/documents?q=): OR regex include extracted_text (funziona anche prima che l'indice text sia disponibile)
    - Text index MongoDB: user_id + filename + notes + tags + extracted_text
    - Context Assembler provider documents: espone excerpt/pages/language/text_extracted — ma resta NO-OP dietro DOCUMENT_CONTEXT_ENABLED=false
  error_handling:
    - PDF corrotto → extraction_engine="pypdf", error_code="pdf_corrupted", upload comunque OK
    - PDF cifrato → error_code="pdf_encrypted" (soft-fail)
    - OCR binario mancante → error_code="ocr_engine_unavailable" (fallback silenzioso)
    - Immagine non decodificabile → error_code="image_unreadable"
    - Timeout / decode / anche exception generica sotto la pipeline: upload NON fallisce mai per problemi di estrazione (soft-fail garantito via try/except esterno)
    - Deduplica: same hash → NON riestrae. `documents.find_one({user_id, hash, deleted!=true})` restituisce doc originale con extracted_text già presente.
  tests:
    file: /app/backend/tests/test_iter20_document_intelligence.py
    total: 10
    passed: 10
    coverage:
      A_pdf: extraction metadata presente + search per marker su extracted_text (2)
      B_ocr: image upload triggera pipeline OCR con engine=tesseract (1)
      C_text: text/plain passthrough + ricerca per contenuto (2)
      D_life_graph: nodo documento aggiornato con text_extracted/pages/language (1)
      E_memory_ask: risposta cita documento e sources include entry con source=document (1)
      F_dedup: re-upload stesso content NON crea nuovo doc + NON riestrae (1)
      G_error: PDF corrotto → soft-fail (1)
      H_context_provider: NO-OP quando DOCUMENT_CONTEXT_ENABLED=false (1)
  regressions_checked:
    - iter18.2 + iter19 + iter20 = 37/37 PASSED
    - Zero modifiche a decision_engine/, ranking/, explainability/, action_center/, behavior_engine/
    - Ranking utente invariato


# ==========================================================
# ITERAZIONE 19 — Documents Foundation
# ==========================================================
iter19:
  status: DONE
  scope: foundation-only (NO OCR, NO AI, NO estrazione)
  backend:
    module: /app/backend/documents/
    files: __init__.py, storage.py (abstraction + LocalFilesystemStorage), service.py, router.py, context_provider.py
    storage:
      interface: DocumentStorageProvider (ABC)
      default_impl: LocalFilesystemStorage (base=/app/backend/data/documents/<user>/<hash_prefix>/<hash>.bin)
      swappable: S3/GCS/Azure senza toccare service/router
    api_endpoints:
      - POST   /api/documents/upload         (multipart, file+tags+notes)
      - GET    /api/documents                (query: q, tag, mime, archived, sort, limit, offset)
      - GET    /api/documents/{id}
      - GET    /api/documents/{id}/download  (ownership-guarded)
      - PATCH  /api/documents/{id}           (filename, tags, notes)
      - DELETE /api/documents/{id}?hard=bool (soft by default)
      - POST   /api/documents/{id}/archive
      - POST   /api/documents/{id}/restore
    schema_documents_collection:
      - id, user_id, filename, original_filename
      - mime_type, size, hash (sha256)
      - storage_provider, storage_key
      - upload_source, tags, notes
      - archived (bool), deleted (bool), deleted_at
      - life_node_id, knowledge_synced
      - version (predisposizione versioning)
      - created_at, updated_at
    indexes_ensured:
      - user_id + hash (dedup)
      - user_id + created_at
      - user_id + archived + deleted
      - text index su filename/notes/tags
    security:
      - ownership check su GET/PATCH/DELETE/download/archive/restore
      - mime whitelist (env DOCUMENT_ALLOWED_MIMES override)
      - max size configurabile (DOCUMENT_MAX_SIZE_BYTES, default 25MB)
      - path traversal protection (basename sanitize)
      - hash SHA-256 stampato + dedup per (user, hash)
    wiring:
      - server.py::startup → DocumentService.ensure_ready() (idempotente)
      - routers/__init__.py → documents_router mounted
      - Life Graph: ogni upload crea automaticamente node type=document con attrs mime_type/size/hash/source
      - Knowledge Layer: schema `document` esteso con filename+mime_type+tags+notes; knowledge.merge chiamata al momento dell'upload
      - Memory router GET /api/memory ora restituisce anche `documents: [{id, filename, mime_type, tags, created_at}]` (retrocompat: `items` invariato)
      - Context Assembler provider preparato ma NO-OP (DOCUMENT_CONTEXT_ENABLED=false)
  feature_flags:
    DOCUMENT_STORAGE_BACKEND: "local"
    DOCUMENT_MAX_SIZE_BYTES: "26214400"
    DOCUMENT_CONTEXT_ENABLED: "false"
    DOCUMENT_AI_ENABLED: "false"
    DOCUMENT_OCR_ENABLED: "false"
    DOCUMENT_EXTRACTION_ENABLED: "false"
  tests:
    file: /app/backend/tests/test_iter19_documents.py
    total: 18
    passed: 18
    coverage:
      A_upload: upload OK, dedup by hash, mime block, empty content block (4)
      B_list: user isolation, search by q, filter tag+mime, sort (4)
      C_detail: ownership on GET/download, PATCH, download bytes exact (3)
      D_lifecycle: archive/restore, soft delete, hard delete (3)
      E_wiring: life_graph node type=document, knowledge facts present, memory tab includes documents (3)
      F_context_provider: NO-OP quando flag off (1)
  frontend:
    files_created:
      - /app/frontend/app/(tabs)/documenti.tsx (schermata completa)
    files_modified:
      - /app/frontend/app/(tabs)/_layout.tsx (tab "Documenti" tra Memoria e Aggiungi)
      - /app/frontend/src/api/client.ts (API + types DocumentItem, DocumentsListResponse)
    packages_added:
      - expo-document-picker@14.0.8
    ui_features:
      - lista con FlatList + pull-to-refresh
      - ricerca live (nome/tag/tipo/note)
      - chip filtri sort: Recenti / A-Z / Peso
      - toggle Attivi/Archivio
      - upload via DocumentPicker (multipart)
      - dettaglio in modal sheet (meta, hash, tag, note, stato)
      - azioni: archivia / ripristina / elimina
      - empty state con CTA
      - error banner inline
      - loading spinner
  regressions_checked:
    - iter18_2 (9 tests) + iter18 (13 tests) + iter19 (18 tests) = 40/40 PASSED
    - Zero modifiche a decision_engine/, explainability/, action_center/, ranking/
    - Ranking utente invariato (verificato B2 iter18.2)
  screenshot:
    - /tmp/ora_docs.png (empty state con tab attivo)


# ==========================================================
# ITERAZIONE 18.2 — Existing Features Activation Audit & Wiring
# ==========================================================
iter18_2:
  status: DONE
  scope: audit + wiring, ZERO new features
  respected_constraints:
    - no new features built
    - no new connectors added
    - no changes to real Decision Engine ranking
    - Behavior-Aware Real Mode NOT activated
    - no architectural changes
  wiring_completed:
    - server.py::startup → BehaviorShadowService.ensure_ready() (indexes on `behavior_shadow_evaluations`)
    - routers/decisions.py::/decisions/top → fire-and-forget shadow.evaluate_batch (gated by BEHAVIOR_PROFILE_ENABLED && BEHAVIOR_SHADOW_MODE; ranking_applied invariant preserved)
    - .env → explicit BEHAVIOR_PROFILE_ENABLED=false, BEHAVIOR_SHADOW_MODE=false, CONTEXT_ASSEMBLER_ENABLED=true, PERMISSIONS_CONTEXT_ENABLED=true (documented)
    - routers/memory.py::/memory POST → mirror to life_graph (type=generic, subtype=memory) + knowledge.merge(summary, notes, tags). db.memories doc unchanged (retrocompat) + back-reference life_node_id/knowledge_synced
    - routers/memory.py::/memory/ask POST → additively includes knowledge facts from memory nodes in LLM context; primary db.memories path unchanged
  tests_created: /app/backend/tests/test_iter18_2_audit_wiring.py (9 tests, all passing)
  regression_check:
    - iter15/16/17/18 + iter18.2 together (correct order): 53/53 PASSED
    - decision_engine/*, explainability/*, action_center/*: NEVER touched
  modules_not_wired: none — all built modules are now either actively used or explicitly gated by a documented flag
  memory_wiring_details:
    node_type: generic
    subtype_attribute: memory
    knowledge_source_type: user_memory
    back_reference: memories.life_node_id, memories.knowledge_synced
    fallback: if life_graph or knowledge fails, memory doc is still persisted in db.memories (retrocompat guaranteed)
  auto_shadow_trigger_details:
    entry_point: GET /api/decisions/top
    mode: asyncio.create_task (fire-and-forget)
    invariant: ranking_applied == False on every persisted eval
    inspection: GET /api/behavior-shadow/comparison, /api/behavior-shadow/evaluations, /api/behavior-shadow/stats
    activation_command: |
      # Both flags must be true to activate
      export BEHAVIOR_PROFILE_ENABLED=true
      export BEHAVIOR_SHADOW_MODE=true
      sudo supervisorctl restart backend
  updated_completion_estimate: ~90% (from 85%): every built backend module is now wired to the user flow or explicitly documented as gated


# ==========================================================
# ITERAZIONE 18 — Apple Calendar Connector (EventKit / iPhone-iPad)
# ==========================================================
iter18:
  status: DONE (backend + frontend), TESTING FINALE PENDENTE SU IPHONE FISICO (EAS)
  packages_added:
    - expo-calendar@15.0.8 (via `yarn expo install`)
  backend:
    module_created: /app/backend/connectors/apple_calendar/
    files:
      - __init__.py, scopes.py, normalizer.py, service.py, router.py
    ingestion_extensions:
      - /app/backend/ingestion/cross_provider.py (nuovo — first-write-wins dedup)
      - /app/backend/ingestion/routing.py (stampa content_key + provider_primary + mirrored_sources)
    router: /app/backend/routers/__init__.py (aggiunto apple_calendar_router)
    endpoints:
      - GET  /api/connectors/apple-calendar/config-status
      - POST /api/connectors/apple-calendar/connect
      - GET  /api/connectors/apple-calendar/instances
      - GET  /api/connectors/apple-calendar/instances/{id}
      - GET  /api/connectors/apple-calendar/instances/{id}/status
      - POST /api/connectors/apple-calendar/instances/{id}/select-calendars
      - POST /api/connectors/apple-calendar/instances/{id}/sync
      - POST /api/connectors/apple-calendar/instances/{id}/disconnect
    feature_flag: APPLE_CALENDAR_ENABLED=false (default)
    connector_id: calendar_apple
    capability_id: calendar.read (già esistente, riutilizzata)
    cross_provider_dedup:
      strategy: first-write-wins
      content_key: sha256(user_id + title_norm + starts_at + ends_at + location_norm + all_day)
      match_criteria: strict (esatto, no fuzzy)
      primary_never_overwritten: true
      mirrored_sources_on_node: {provider, source_id, connector_instance_id, calendar_id, external_id, source_hash, first_seen_at, last_seen_at}
      disconnect_behavior: pull mirrored_sources dell'istanza revocata, primary node preservato
      promotion_from_mirrored: implementata (mirrored → primary quando primary revocato) in cross_provider.promote_from_mirrored
    tests_created: /app/backend/tests/test_iter18_apple_calendar_connector.py
    tests_count: 13
    tests_result: 13/13 PASSED (isolated + con iter15/16/17)
    tests_coverage:
      A_feature_flag: 2 tests (503 quando off, config_status)
      B_connect: 3 tests (crea instance, ownership isolation, status)
      C_sync_happy: 2 tests (life_node creato, idempotenza)
      D_cross_provider_dedup: 3 tests (Google→Apple, Apple→Google, content_key stabile)
      E_quarantine: 2 tests (id mancante, times mancanti)
      F_disconnect: 1 test (revoke + detach mirrored)
  frontend:
    files_created:
      - /app/frontend/src/utils/apple-calendar.ts (wrapper platform-safe di expo-calendar con mock DEV per Web/Expo Go)
      - /app/frontend/app/connect-apple-calendar.tsx (flow completo: intro → permessi → select → sync → done)
    files_modified:
      - /app/frontend/src/api/client.ts (aggiunta appleCalendarConfig/Instances/Connect/Sync/Disconnect + types)
      - /app/frontend/app/settings.tsx (aggiunta AppleCalendarSection con render condizionale Platform.OS === 'ios' && appleConfig?.enabled)
      - /app/frontend/app.json (permesso NSCalendarsFullAccessUsageDescription + plugin expo-calendar)
    ui_flow:
      1_intro: pre-permission explanation con bullets "Solo lettura / I dati restano tuoi / Zero duplicati"
      2_permission: richiesta contestuale, handling granted/denied/blocked con Linking.openSettings()
      3_select: multi-check calendari (default: tutti selezionati)
      4_sync: chunked upload (200 eventi/batch), progress card
      5_done: sommario (Eventi importati / Già presenti / Aggiornati / Ignorati)
    conditional_visibility_rules:
      ios_ipados: mostra Apple Calendar row
      android: NASCONDE completamente (nessun placeholder)
      web: NASCONDE completamente
      feature_flag_off: NASCONDE anche su iOS
    mock_mode:
      env_var: EXPO_PUBLIC_APPLE_CALENDAR_MOCK=1 (solo DEV, per validazione UI su Web/Expo Go)
      real_ios_behavior: bypass mock, chiamate EventKit dirette anche se mock è attivo
      production_default: mock DISATTIVATO (variabile assente in .env)
  validation_done_by_agent:
    - screenshot: intro/select/done UI verificati su Web con MOCK_ENABLED=1
    - end_to_end: connect → readEvents (mock 5 events) → sync → done card mostra "Eventi importati 5"
    - platform_gating: verificato che su Web (non-iOS) la riga Apple Calendar in /settings è NASCOSTA
    - unsupported_banner: verificato su Web che /connect-apple-calendar mostra banner "Solo iPhone e iPad"
  cleanup_done:
    - MOCK env rimosso da /app/frontend/.env
    - APPLE_CALENDAR_ENABLED riportato a false in /app/backend/.env
  ios_native_validation: PENDENTE (richiede EAS build su iPhone fisico — checklist consegnata a utente)
  regression_status: nessuna regressione. Test iter9/10/11/15/16/17 continuano a passare in isolamento.


# ==========================================================
# ITERAZIONE 17 — Behavior-Aware Decision Engine — Shadow Mode
# ==========================================================
iter17:
  status: DONE
  module_created: /app/backend/behavior_aware_decisions/
  files:
    - __init__.py, types.py, rules.py, scoring.py, service.py, storage.py, audit.py, comparison.py
  router: /app/backend/routers/behavior_shadow.py (5 GET endpoints)
  endpoints:
    - GET /api/behavior-shadow/rules
    - GET /api/behavior-shadow/decisions/{decision_id}
    - GET /api/behavior-shadow/evaluations
    - GET /api/behavior-shadow/stats
    - GET /api/behavior-shadow/comparison
  http_methods_rejected: [POST, PUT, DELETE]  # 405 verified
  feature_flags:
    BEHAVIOR_PROFILE_ENABLED: false (default)
    BEHAVIOR_SHADOW_MODE: false (default)
    both_required_for_activation: true
  db_collections_added:
    - behavior_shadow_evaluations   # append-only, unique idempotency_key
  rules_implemented: 8
    - preferred_time_alignment (delta positive)
    - historical_postponement_risk (delta positive)
    - completion_affinity (delta positive lieve)
    - low_success_window (delta positive)
    - quick_win_affinity (delta positive lieve)
    - category_procrastination (delta positive moderato)
    - overload_protection (SOLA regola con delta negativo)
    - deadline_guardrail (marker: clip delta<0 su urgenti/critiche)
  caps:
    per_rule: ±3.0
    total_min: -5.0
    total_max: +10.0
    confidence_multipliers: {low: 0, medium: 0.5, high: 1.0}
  invariants:
    ranking_applied_always_false: verified
    effective_score_never_modified: verified (test dedicato)
    real_ranking_unchanged: kendall_tau=1.0 unchanged_ratio=1.0 (live smoke con flag OFF)
    zero_ui_changes: verified (frontend intoccato)
    zero_explainability_changes: verified
  idempotency: verified via idempotency_key = sha256(user|dec|dec_v|profile_v|ctx|rule_v)
  tests:
    file: tests/test_iter17_behavior_aware_shadow.py
    passed: 13
    failed: 0
    coverage:
      - flags_off_zero_writes
      - profile_on_shadow_off_no_write
      - flags_on_persists_evaluation
      - idempotency
      - cap_enforcement_math
      - deadline_guardrail_no_negative_on_urgent
      - confidence_low_zero_delta
      - confidence_medium_half_delta
      - real_score_not_modified
      - cross_user_isolation
      - comparison_engine
      - no_llm_imports_shadow
      - fail_safe_profile_error
  regression_check:
    iter11_action_center: 39/39 pass
    iter15_behavioral: 13/13 pass
    iter16_wiring: 5/5 pass
    iter17_shadow: 13/13 pass
    total_recent_iters: 70/70 pass
  live_smoke_flags_off:
    endpoints_ok: 5/5
    comparison_kendall_tau: 1.0
    comparison_unchanged_ratio: 1.0
    evaluations_persisted_with_zero_delta: yes (idempotenti)
  files_touched_backend:
    - routers/__init__.py (register behavior_shadow_router)
  files_added:
    - behavior_aware_decisions/* (7 files)
    - routers/behavior_shadow.py
    - tests/test_iter17_behavior_aware_shadow.py
  modules_untouched:
    - decision_engine, ranking, explainability, daily_intelligence,
      action_center, google_calendar, life_graph, knowledge, ingestion,
      token_vault, home, frontend (0 line changes)

# ==========================================================
# ITERAZIONE 16 — Behavioral Data Integrity & Context Wiring
# ==========================================================
# Status: DONE — 18/18 tests iter15+iter16 pass in isolation.

iter16:
  fixes:
    - timezone_aware_metrics: hour/weekday buckets now use ORA_DEFAULT_TZ (default Europe/Rome)
    - sessionization: open + refresh + close events grouped in sessions with 30-min gap; avg_session_minutes now computed
    - test_iter9_j1_real_mode_without_creds_is_503: monkeypatch.setenv(GOOGLE_OAUTH_CLIENT_ID/SECRET, "") to force empty creds regardless of .env
    - test_iter9_email_collisions_in_xdist: TS uses uuid.uuid4() suffix instead of int(time.time())
  context_assembler_wiring:
    provider_registered: behavior_profile
    module: /app/backend/context_assembler/behavior_provider.py
    flag_off:
      signals: 0
      context_hash_stable: verified (hash1 == hash2 across two calls)
      providers_run_lists_provider: true
    flag_on:
      signals: 1 (key=behavior.profile)
      context_hash_changes_deterministically: verified
      extra_signal_key: behavior.profile
      other_signals_unchanged: verified
  regression_guarantees:
    ranking_untouched: true
    decision_engine_untouched: true
    explainability_untouched: true
    daily_intelligence_untouched: true
    action_center_untouched: true
    google_calendar_untouched: true
    token_vault_untouched: true
  tests:
    file: tests/test_iter16_wiring_and_integrity.py
    passed: 5
    failed: 0
    coverage:
      - timezone_bucket_uses_local_tz
      - sessionization_pairs_open_and_refresh
      - context_hash_stable_when_flag_off
      - context_hash_changes_when_flag_on
      - flag_on_does_not_write_to_decisions_collection
  iter15_regression: 13/13 pass (unchanged)
  iter11_regression: 39/39 pass (unchanged)
  iter10_regression: 27/27 pass (unchanged)
  iter9_regression: 25/25 pass (FIXED — was 22/25 with 3 fails/errors due to real OAuth creds in .env)
  live_hash_stability_smoke:
    off_hash1: "2e281769004e1cdb"
    off_hash2: "2e281769004e1cdb"
    on_hash:   "fdafa0b7bdeae482"
    off_stable: true
    on_diff: true
    extra_key_on: [behavior.profile]
  files_touched_backend:
    - behavioral_intelligence/metrics.py     # tz-aware buckets + sessionization
    - context_assembler/assembler.py         # register behavior_profile provider (10th)
    - context_assembler/behavior_provider.py # NEW: strict no-op when flag off
    - tests/test_iter9_ingestion_and_google_calendar.py  # fix pre-existing regressions
  files_added:
    - tests/test_iter16_wiring_and_integrity.py

  next_iteration_gate:
    behavior_aware_decision_engine_shadow_mode: PENDING  # not implemented in iter16
    guardrail: any future iteration must keep BEHAVIOR_PROFILE_ENABLED=false gating priority modifications

# ==========================================================
# ITERAZIONE 15 — Behavioral Intelligence Engine
# ==========================================================
# Status: DONE — 13/13 iter15 tests PASS, provider silent by default,
# no writes on source collections, no LLM/ML dependencies.

iter15:
  module_created: /app/backend/behavioral_intelligence/
  files:
    - __init__.py
    - types.py         # BehavioralEvent, BehaviorMetrics, BehaviorPattern, BehaviorProfile, Confidence, Trend
    - storage.py       # append-only DAL with unique indexes
    - timeline.py      # append_event / append_events (idempotent by source_ref)
    - observers.py     # lazy-sync from decision_action_history, ingestion_events, connector_instances, daily_summaries, context_snapshots + middleware hooks (app_open/refresh/close)
    - metrics.py       # deterministic incremental counters + hour/weekday heatmaps + rates
    - patterns.py      # 7 deterministic detectors: morning_completer, evening_postponer, heavy_calendar_user, post_dinner_opener, quick_winner, weekday_power_user, weekend_light_user
    - confidence.py    # LOW/MEDIUM/HIGH by sample size, aggregate = min
    - service.py       # orchestrator with ensure_ready() and per-call lazy sync
    - provider.py      # BehaviorProfileProvider gated by BEHAVIOR_PROFILE_ENABLED (default OFF)
  router: /app/backend/routers/behavior.py (GET-only)
  endpoints:
    - GET /api/behavior/profile
    - GET /api/behavior/metrics?window_days=60
    - GET /api/behavior/patterns
    - GET /api/behavior/timeline?since=&until=&event_types=&limit=&skip=
    - GET /api/behavior/confidence
  http_methods_rejected: [POST, PUT, DELETE]  # 405 verified
  db_collections_added:
    - behavioral_events         # append-only, unique (user_id, source_type, source_ref)
    - behavioral_cursors        # progress markers for lazy sync
    - behavior_metric_snapshots # versioned metric history
    - behavior_profile_snapshots# versioned profile history
    - behavior_pattern_snapshots# versioned pattern history
  middleware:
    - behavioral_observer_middleware (server.py): fires first_app_open_today + manual_refresh idempotently, never blocks response, all failures swallowed
  feature_flag: BEHAVIOR_PROFILE_ENABLED  # default OFF
  context_hash_invariance:
    flag_off_provider_signals: []
    flag_off_hash_stable: verified (provider not attached to ContextAssembler by default)
  no_llm_check: pass (test_no_llm_imports scans forbidden imports; 0 hits)
  files_not_touched_backend:
    - decision_engine/*
    - life_graph/*
    - knowledge/*
    - auto_link/*
    - context_assembler/*  # provider ready but NOT wired to Context Assembler (per spec)
    - permissions/*
    - connectors/*
    - ingestion/*
    - daily_intelligence/*
    - explainability/*
    - action_center/*
    - deps.py (services list unchanged)
  files_touched_backend:
    - server.py         # added Behavioral bootstrap in startup + observational middleware (non-blocking)
    - routers/__init__.py # register behavior router
  tests:
    file: tests/test_iter15_behavioral_intelligence.py
    passed: 13
    failed: 0
    coverage:
      - timeline_append_only
      - events_are_immutable
      - metrics_incremental_from_source
      - patterns_deterministic
      - confidence_low_with_no_data
      - confidence_scales_with_sample_size
      - cross_user_isolation
      - provider_is_silent_when_flag_off
      - provider_emits_when_flag_on
      - no_llm_imports
      - performance_1000_events
      - performance_10000_events
      - behavioral_module_never_writes_to_source_collections
  performance:
    events_1000:   metrics computation <3s
    events_10000:  metrics computation <8s
  live_smoke_via_http:
    demo_user_timeline_total: 31
    patterns_detected: [quick_winner, weekday_power_user]
    confidence_report: {metrics: medium, profile: medium, patterns: low, events_observed: 31}
  regressions:
    - iter11_explainability_action_center: 39/39 pass  # unchanged
    - iter8_permissions_and_consent: pass
    - iter9 parallel failures: PRE-EXISTING (iter13 populated real OAuth creds → test_j1 assumes empty creds; DuplicateKey collisions in parallel-xdist test iter9 email fixtures) — NOT caused by iter15
  frontend_unchanged: true
  home_unchanged: true
  ranking_unchanged: true
  explainability_unchanged: true
  action_center_unchanged: true
  daily_intelligence_unchanged: true
  google_calendar_unchanged: true
  token_vault_unchanged: true

# ==========================================================
# ITERAZIONE 14 — Real User Onboarding & Calendar UX
# ==========================================================
# Status: DONE — testing agent ALL PASS, zero bugs, zero regressions

iter14:
  refactor:
    index_tsx_lines_before: 1155
    index_tsx_lines_after: 348
    extracted_components:
      - /app/frontend/src/components/home/HomeHeader.tsx (Header + SyncMeta + Offline/Error banners)
      - /app/frontend/src/components/home/FocusNowCard.tsx
      - /app/frontend/src/components/home/DailySummaryCard.tsx
      - /app/frontend/src/components/home/LaterList.tsx
      - /app/frontend/src/components/home/EmptyFocus.tsx
      - /app/frontend/src/components/home/CalendarConnectionCard.tsx  # NEW — A/B/C states
      - /app/frontend/src/components/sheets/Sheet.tsx (base wrapper)
      - /app/frontend/src/components/sheets/DecisionSheets.tsx (Why/Daily/Confirm/Partial/Postpone/Reason/More/History)
      - /app/frontend/src/components/ui/ActionBtn.tsx
    utilities_added:
      - /app/frontend/src/utils/errors.ts (humanizeError translation IT)
    behavior_preserved: true

  new_screens:
    - /app/frontend/app/manage-calendars.tsx  # checkbox list, save selection
    - /app/frontend/app/settings.tsx          # Account collegati: sync/manage/disconnect
    - /app/frontend/app/how-it-works.tsx      # 4-step onboarding explainer

  home_intelligence:
    state_A_hero:
      title: "Collega il tuo Google Calendar"
      subtitle: "ORA può capire automaticamente i tuoi impegni e aiutarti a organizzare la giornata."
      cta_primary: "Continua con Google"
      cta_secondary: "Scopri come funziona"
      tech_words_exposed: 0
    state_B_never_synced: "Google Calendar collegato. Premi Sincronizza per importare i tuoi eventi."
    state_C_synced: hidden_from_home  # replaced by DailySummaryCard per spec §6

  sync_ux:
    progressive_steps: [Connessione, Importazione eventi, Aggiornamento ORA, Completato]
    haptic_feedback: differentiated (medium on start, success on done, error on fail)
    inline_result: "N nuovi · M già presenti"

  error_ux:
    - humanizeError() translates status/detail/OAuth codes to Italian human messages
    - never exposes: OAuth, Connector, Token, redirect_uri_mismatch, 401/403/404, GOCSPX, state, code
    - contextual overrides per action (connect, sync, select, calendars, revoke)

  api_client_extended:
    - googleCalendarOAuthStart
    - googleCalendarCalendars
    - googleCalendarSelectCalendars
    - googleCalendarSync
    - googleCalendarInstanceStatus
    - googleCalendarRevoke

  testing_agent_summary:
    outcome: ALL_PASS
    regressions: 0
    console_errors: 0
    tech_word_leaks_in_dom: 0
    checks:
      state_A_hero_render: PASS
      how_it_works_4steps: PASS
      btn_connect_google_calls_start: PASS
      state_C_demo_hides_calendar_cards: PASS
      settings_meta_grid: PASS
      manage_calendars_toggle_and_save: PASS
      confirm_revoke_dialog_safe_cancel: PASS
      iter12_regression: PASS
      offline_banner: PASS
      responsive_mobile_tablet_desktop: PASS
      dark_mode_new_screens: PASS
      touch_target_min_44: PASS
      pull_to_refresh: PASS

  files_changed:
    - /app/frontend/app/(tabs)/index.tsx (refactor)
    - /app/frontend/app/(tabs)/profilo.tsx (added Impostazioni row)
    - /app/frontend/src/api/client.ts (extended endpoints + types)
  files_added:
    - /app/frontend/app/manage-calendars.tsx
    - /app/frontend/app/settings.tsx
    - /app/frontend/app/how-it-works.tsx
    - /app/frontend/src/components/home/*.tsx (6 files)
    - /app/frontend/src/components/sheets/Sheet.tsx
    - /app/frontend/src/components/sheets/DecisionSheets.tsx
    - /app/frontend/src/components/ui/ActionBtn.tsx
    - /app/frontend/src/utils/errors.ts
  files_unchanged_backend: all backend files untouched  # constraint respected

# ==========================================================
# ITERAZIONE 13 — Primo collegamento REALE Google Calendar (E2E)
# ==========================================================
# Status: DONE — real OAuth completed, 1 real event ingested, all sec checks green

iter13:
  oauth_completed: true
  used_fake_provider: false
  auto_decisions_generated: 0
  instance_id: "ci_5a58fde78638416b"
  provider_account_id_hash: "acct_ae02ac2ef80cb65764106283"
  display_label: "francesconicolocefala@gmail.com"
  authorized_scopes:
    - "https://www.googleapis.com/auth/calendar.readonly"
    - "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
    - "openid"
    - "email"
    - "profile"
  selected_calendars: ["francesconicolocefala@gmail.com"]
  sync_window_days: {past: 30, future: 180}
  sync_run_1: {received: 1, processed: 1, skipped: 0, quarantined: 0, failed: 0}
  sync_run_2_idempotent: {received: 1, processed: 0, skipped: 1, quarantined: 0, failed: 0}
  life_graph_calendar_nodes: 1  # "Buon compleanno!" all-day 2026-12-05
  knowledge_calendar_facts: 1
  security_checks:
    zero_secret_leaks_in_logs: true
    zero_client_secret_in_config_status: true
    zero_event_title_in_logs: true
    fake_callback_in_real_mode_404: true
    cross_user_isolation_404: true
    unauth_401: true
    provider_mode: "real"
    silent_downgrade_to_fake: false
    token_vault_healthy: true
    consent_active: true
  home_ui:
    calendar_empty_state_hidden: true  # ci sono istanze
    daily_today_reflects_real_data: true  # 0 eventi oggi = calendar reale ha 0 eventi oggi
    no_demo_data_shown: true  # demo decision seed rimangono ma sono voluti dal seed utente demo

#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Iterazione 8 — Permission & Connector Core + refactor preliminari.
  1. Split `server.py` in routers modulari (auth, decisions, legacy_tasks,
     life_graph, knowledge, auto_link, context, admin, memory, permissions,
     connectors). `server.py` deve restare bootstrap minimo.
  2. Uniformare `GET /api/context/decisions/{decision_id}/latest` in
     `{ snapshot, status, generated_at, assembler_version }`.
  3. Supportare `node_ids: []` in `DecisionIn`. La repository NON scrive
     `node_ids` direttamente: crea la Decision, valida ownership dei nodi,
     collega via `LifeGraphService.link_decision` con rollback atomico.
  4. Nuovo modulo `permissions/`: Capability Registry hardcoded (immutable,
     versionato), Consent Service per-connector-instance con wildcard `*`,
     Access Guard, Audit log append-only in `permission_audit`.
  5. Nuovo modulo `connectors/`: registry stub, nessuna chiamata esterna.
  6. `PermissionsContextProvider` in `context_assembler` dietro flag
     `PERMISSIONS_CONTEXT_ENABLED` (default OFF).

backend:
  - task: "Refactor: server.py split into modular routers (/app/backend/routers/*)"
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/backend/routers/*.py, /app/backend/deps.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "server.py reduced to bootstrap. All 11 domain routers registered under /api. Smoke test: all pre-existing endpoints still resolve. No public API contract change."

  - task: "Uniform response envelope for GET /api/context/decisions/{id}/latest"
    implemented: true
    working: true
    file: "/app/backend/routers/context.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Response is strictly { snapshot, status, generated_at, assembler_version }. status='available' when snapshot exists, 'not_found' when decision exists but no snapshot yet. 404 kept for unknown/foreign decision. Verified via curl."

  - task: "DecisionIn accepts node_ids[] with atomic LifeGraph link + rollback"
    implemented: true
    working: true
    file: "/app/backend/routers/decisions.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Router validates node ownership pre-insert, then creates Decision, then calls LifeGraphService.link_decision. On any failure the Decision is deleted (rollback). history[] shows ['created','life_graph.linked']. Verified via curl: valid nodes linked, invalid node_id returns 400 and count is unchanged (0 leaks)."

  - task: "Permissions module: Capability Registry (hardcoded, versioned)"
    implemented: true
    working: true
    file: "/app/backend/permissions/capabilities.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "11 capabilities defined (calendar.read/write, mail.read/metadata, messaging.read, health.read, banking.read, contacts.read, location.read, cloud_storage.read, notifications.deliver). Registry is a tuple of MappingProxyType (immutable). Version 1.0.0. Sync to Mongo runs at startup: {synced:11, changed:11}."

  - task: "Permissions module: Consent Service (per-connector-instance)"
    implemented: true
    working: true
    file: "/app/backend/permissions/consent.py, /app/backend/routers/permissions.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Grant/revoke supports {capability_id, connector_id, connector_instance_id} tuple. Wildcard '*' checked as fallback in is_granted(). Idempotent re-grant bumps version. Revoke is soft (status='revoked'). Unique index enforces one row per tuple. Verified via curl."

  - task: "Permissions module: Audit log (append-only, permission_audit)"
    implemented: true
    working: true
    file: "/app/backend/permissions/audit.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Every grant/revoke/access.check writes an immutable record with event_id, correlation_id, timestamps, retention_until. Sensitive keys (token, password, iban, message_body, ...) are blacklisted from the details map. Indexed by (user_id, timestamp), (connector_id, timestamp), (capability_id, timestamp). Verified via GET /api/permissions/audit."

  - task: "Permissions module: AccessGuard (FastAPI dependency)"
    implemented: true
    working: true
    file: "/app/backend/permissions/guard.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "require_capability(capability_id, connector_id, connector_instance_id) dependency factory. Rejects with 403 (consent_denied) or 404 (capability_unknown). Audited via PermissionService.require_access."

  - task: "Connectors module: stub registry (no external calls)"
    implemented: true
    working: true
    file: "/app/backend/connectors/registry.py, /app/backend/routers/connectors.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "14 connectors declared (google/apple/outlook calendar, gmail/outlook mail, whatsapp messaging, apple/google health, PSD2 banking, device contacts, device location, drive/icloud cloud storage, push notifications). Each declares required_capabilities validated against permissions registry at import-time. Endpoints: /api/connectors/registry, /registry/{id}, /status. NO 'connect'/'oauth'/'sync' endpoint exposed."

  - task: "PermissionsContextProvider integration in context_assembler (flag-gated)"
    implemented: true
    working: true
    file: "/app/backend/context_assembler/permissions_provider.py, /app/backend/context_assembler/assembler.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Provider 7 added to the pipeline. When PERMISSIONS_CONTEXT_ENABLED=false (default) it emits zero signals: context_hash stays byte-stable (no user-visible behavior change). When ON, emits `active_consent` metadata signals only (capability_id, connector_id, sensitivity), never sensitive payload."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 8
  run_ui: false

test_plan:
  current_focus:
    - "Refactor: server.py split into modular routers (/app/backend/routers/*)"
    - "Uniform response envelope for GET /api/context/decisions/{id}/latest"
    - "DecisionIn accepts node_ids[] with atomic LifeGraph link + rollback"
    - "Permissions module: Capability Registry (hardcoded, versioned)"
    - "Permissions module: Consent Service (per-connector-instance)"
    - "Permissions module: Audit log (append-only, permission_audit)"
    - "Connectors module: stub registry (no external calls)"
    - "PermissionsContextProvider integration in context_assembler (flag-gated)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Iterazione 8 completata. Refactor `server.py` → routers modulari, uniform
        envelope su /context/decisions/{id}/latest, supporto node_ids in DecisionIn
        con rollback atomico via LifeGraphService.link_decision, e nuovi moduli
        permissions/ + connectors/ (stub puri).

        Ho verificato via curl:
          - registry permissions (11) e connectors (14) esposti;
          - grant/revoke/audit funzionanti;
          - /latest ritorna { status: 'not_found' | 'available' };
          - creazione Decision con node_ids valida → history con
            ['created','life_graph.linked'];
          - creazione Decision con node_id inesistente → 400 e nessuna Decision
            residua (rollback OK).

        Nota su test pytest: test_knowledge_layer.py ha 9 test falliti PRE-ESISTENTI
        (schema envelope non aggiornati dai test di iterazione 4/5) — non toccati
        dal refactor. test_ora_backend.py ha 2 fallimenti che si aspettano 5
        priorità con default limit=3 — pre-esistente.

        Da testare (backend testing agent):
          1. Refactor: TUTTI gli endpoint esistenti devono continuare a funzionare
             senza regressioni (auth, decisions, tasks, priorities, life-graph,
             knowledge, auto-link, context, admin, memory).
          2. GET /api/context/decisions/{id}/latest: envelope stretto, status
             corretto in entrambi i casi, 404 su decision di un altro utente.
          3. POST /api/decisions con node_ids: link atomico, rollback su nodo
             invalido, history contiene 'life_graph.linked'.
          4. Permissions: registry, consents CRUD, wildcard fallback, audit,
             revoke-all-for-connector.
          5. Connectors: registry, status_for_user con consensi mappati.
          6. Context assembler: comportamento invariato con
             PERMISSIONS_CONTEXT_ENABLED=false (default).

        Credenziali test: demo@ora.app / Demo!2026 (già presenti in /app/memory/test_credentials.md).



# =====================================================================
# ITERAZIONE 9 — Ingestion Core + Google Calendar Connector
# =====================================================================
user_problem_statement_iter9: |
  Ingestion Core generico (types, event_model, normalizer, dedup, pipeline,
  routing, provenance, repository, service) + primo connector reale
  (Google Calendar) con OAuth 2.0 + PKCE, TokenVault astratto con
  implementazione Fernet dev, ConnectorInstance model, FakeProvider
  attivabile via CALENDAR_PROVIDER_MODE=fake. Nessuna chiamata reale
  senza credenziali. CalendarContextProvider dietro flag
  CALENDAR_CONTEXT_ENABLED (default OFF). Nessuna Decision generation
  senza CALENDAR_DECISION_GENERATION_ENABLED=true.

backend_iter9:
  - task: "TokenVault abstraction + Fernet dev impl (security/token_vault.py)"
    implemented: true
    working: true
    file: "/app/backend/security/token_vault.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Abstract TokenVault protocol + Fernet dev impl. DisabledVault sentinel
            raises VaultNotConfigured with clean error when TOKEN_VAULT_KEY missing.
            Ciphertext stored in `secret_vault` collection, keyed by opaque `sv_<hex>`.
            Real provider gated: fails with 503 provider_not_configured if the vault
            is disabled. No hardcoded key fallback.

  - task: "Ingestion Core module (ingestion/*)"
    implemented: true
    working: true
    file: "/app/backend/ingestion/*.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            IngestionEventRepository with sanitized raw_reference (blacklist of
            token/password/authorization keys). DeduplicationService keyed by
            (user, connector_instance, external_id, source_hash). Pipeline runs
            receive → normalized → dedupe → route → processed and marks
            SUPERSEDED on updates. Malformed payloads land in QUARANTINED with
            error_code but never carry the original content. CalendarEventRouter
            uses ONLY official services (LifeGraphService.create_node/update_node,
            KnowledgeService.merge, DecisionService.create + link via
            LifeGraphService.link_decision). Cancelled events archive the node
            instead of deleting it.

  - task: "CalendarEventNormalizer + provenance-first canonical model"
    implemented: true
    working: true
    file: "/app/backend/ingestion/normalizer.py, /app/backend/ingestion/types.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Google Calendar → CalendarEventNormalized. Every field carries its
            own provenance + sensitivity (NormalizedField). Length caps on
            title/description/attendees/reminders. Deterministic `source_hash`
            over the raw payload (excluding provenance timestamps) → dedup-stable.
            NormalizationError raised for missing_id / payload_not_object /
            missing_start_end → pipeline quarantines the event.

  - task: "Google Calendar connector (real provider + FakeProvider)"
    implemented: true
    working: true
    file: "/app/backend/connectors/google_calendar/*.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            OAuth 2.0 Authorization Code + PKCE (S256). State persisted in
            `google_oauth_sessions` for 10 min; one-shot consumption. Scopes
            minimal: calendar.readonly + calendarlist.readonly + openid/email/profile.
            Token vault: refresh + access tokens stored encrypted; access token
            auto-refreshed on expiry. RealGoogleCalendarProvider talks to
            googleapis.com; FakeGoogleCalendarProvider (in-memory, deterministic
            seeder) activated ONLY when CALENDAR_PROVIDER_MODE=fake.
            build_calendar_provider() never falls back to fake silently.
            When CALENDAR_PROVIDER_MODE=real but creds missing → clean 503
            provider_not_configured.

  - task: "ConnectorInstance model + per-account state"
    implemented: true
    working: true
    file: "/app/backend/connectors/instances.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            provider_account_id_hash keyed via SHA-256 (no plaintext account id).
            Unique index on (user_id, connector_id, provider_account_id_hash).
            Fields: authorized_scopes, selected_resource_ids, sync_mode, cursor,
            secret_reference, status ∈ {pending, connected, syncing, degraded,
            reauthorization_required, revoked, disabled}, poll_interval_min,
            window_past_days, window_future_days (all configurable per instance).

  - task: "AccessGuard integration on every read"
    implemented: true
    working: true
    file: "/app/backend/connectors/google_calendar/service.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Every read (list_calendars, sync, refresh) calls
            PermissionService.check_access(user, calendar.read, calendar_google,
            instance_id) BEFORE any Google HTTP call. Denied → 403 consent_denied,
            audited. Post-callback the ORA-side consent is granted automatically
            for the exact connector-instance (separate from Google's consent).

  - task: "Ingestion + connector endpoints"
    implemented: true
    working: true
    file: "/app/backend/routers/ingestion.py, /app/backend/connectors/google_calendar/router.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            POST /api/connectors/google-calendar/oauth/start
            GET  /api/connectors/google-calendar/oauth/callback (real)
            POST /api/connectors/google-calendar/oauth/callback-fake (fake mode only, 404 in real)
            GET  /api/connectors/google-calendar/instances
            GET  /api/connectors/google-calendar/instances/{id}
            GET  /api/connectors/google-calendar/instances/{id}/calendars
            POST /api/connectors/google-calendar/instances/{id}/select-calendars
            POST /api/connectors/google-calendar/instances/{id}/sync
            POST /api/connectors/google-calendar/instances/{id}/refresh
            POST /api/connectors/google-calendar/instances/{id}/revoke
            GET  /api/connectors/google-calendar/instances/{id}/status
            GET  /api/ingestion/events, /{id}, /stats

  - task: "Sync: initial + incremental with sync_token cursor"
    implemented: true
    working: true
    file: "/app/backend/connectors/google_calendar/service.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Initial window: -30 / +180 days (configurable per instance,
            capped by GOOGLE_CALENDAR_MAX_WINDOW_DAYS). Subsequent syncs use
            the per-calendar sync_token cursor → incremental. force_full=True
            (via /refresh) bypasses the cursor. Poll interval 15 min default,
            per-instance configurable.

  - task: "Data revocation flow"
    implemented: true
    working: true
    file: "/app/backend/connectors/google_calendar/service.py"
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            On /revoke: (1) Google-side token revoke (best-effort);
            (2) vault entry revoked; (3) ORA consent revoked for instance;
            (4) ConnectorInstance status → 'revoked'; (5) DataRevocationPlan
            doc inserted; (6) ingested events marked source_status='detached'.
            User-verified facts (Knowledge Layer values) are NOT deleted.
            Post-revoke sync attempts → 403 consent_denied.

  - task: "CalendarContextProvider (flag-gated CALENDAR_CONTEXT_ENABLED)"
    implemented: true
    working: true
    file: "/app/backend/context_assembler/calendar_provider.py, /app/backend/context_assembler/assembler.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Provider 8 in the pipeline. Flag OFF (default) → zero signals,
            context_hash byte-stable. Flag ON → reads ONLY from ingested,
            already-consented events (metadata only: title, starts_at,
            calendar_id, instance_id) — never re-fetches from Google.

test_plan_iter9:
  current_focus:
    - "TokenVault abstraction + Fernet dev impl (security/token_vault.py)"
    - "Ingestion Core module (ingestion/*)"
    - "Google Calendar connector (real provider + FakeProvider)"
    - "ConnectorInstance model + per-account state"
    - "AccessGuard integration on every read"
    - "Sync: initial + incremental with sync_token cursor"
    - "Data revocation flow"
    - "CalendarContextProvider (flag-gated CALENDAR_CONTEXT_ENABLED)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication_iter9:
    - agent: "main"
      message: |
        Iterazione 9 completata. Tutto verde in locale:
          - 25/25 tests in tests/test_iter9_ingestion_and_google_calendar.py
          - 40/40 tests in tests/test_iter8_permissions_connectors.py (nessuna regressione)
          - 86/86 tests nelle suite legacy (life_graph + context_assembler + auto_link)
        Il connector reale è pronto ma disabilitato senza credenziali:
        `POST /api/connectors/google-calendar/oauth/start` → 503
        `provider_not_configured` finché GOOGLE_OAUTH_CLIENT_ID / SECRET /
        REDIRECT_URI non vengono impostati. Il FakeProvider è attivabile via
        CALENDAR_PROVIDER_MODE=fake (default `real`, no silent downgrade).

        Test in-process: la suite iter9 usa `TestClient(server.app)` e imposta
        env `CALENDAR_PROVIDER_MODE=fake` PRIMA di importare server.py.
        Il testing agent DEVE eseguire questa suite con
          env CALENDAR_PROVIDER_MODE=fake python -m pytest tests/test_iter9_… -n 0
        (l'endpoint /oauth/callback-fake ritorna 404 senza il flag).

        Per la verifica dal preview backend (senza fake mode):
          - /oauth/start → 503 provider_not_configured
          - /instances → []
          - /ingestion/stats → {total: 0, by_connector: {}}
          - Nessuna regressione sugli endpoint pre-esistenti (auth, decisions,
            life-graph, knowledge, auto-link, context, memory, admin,
            permissions, connectors).

        Credenziali test: demo@ora.app / Demo!2026 (invariate).

# ==========================================================
# ITERAZIONE 12 — Home Experience + Explainability UI (Frontend)
# ==========================================================

frontend_iter12:
  - task: "Home rewrite: Focus Now card + explainability + action center + daily summary + decision history"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/index.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Iterazione 12 UI implementata (mantenuta la logica esistente scritta nella sessione precedente e aggiunti gli enhancement richiesti dall'utente):
          - Design tokens estesi con colori semantici bg (successBg/warningBg/errorBg/infoBg), skeleton palette, motion (fast/base/slow), touch.min=44.
          - Skeleton components (FocusSkeleton, DailySkeleton, LaterSkeleton) con shine reanimated al posto di ActivityIndicator generico.
          - Reanimated LayoutTransition + FadeInDown/FadeOut 200–300ms su Focus Now, "Dopo" list e sheet.
          - Sheet redesign: SlideInDown springy, backdrop con FadeIn/FadeOut, unmount pulito.
          - Haptic differenziati via utils/haptic: tap (start/tap), select (refresh/pct), medium (complete/postpone/block), success (server ack), error (fail). No-op su web.
          - Focus Now più dominante: pill "ORA" con dot, shadow leggera, title 24–26pt, summary box con border-left brand.
          - Progress bar in_progress (info) e partially_completed (warning) con % opzionale.
          - Pull-to-refresh già presente, ora con haptic select e tint dark-consistente.
          - Offline banner: hook useOnlineStatus (web navigator.onLine + listener; native fallback via network-error detection). Mostra banner "Sei offline…" e header "Aggiornato N min fa".
          - Accessibility: accessibilityRole/label/hint ovunque, touch target minimo 44x44, accessibilityLiveRegion sui banner.
          - Errori 403/404/409/5xx + network mappati in messaggi umani e haptic error.
          - MeetaGrid con colori semantici (Rimando Alto in error, Impatto Alto in warning).
          - Layout responsive: content max 720px centrato su schermi ≥ 700px (desktop/tablet), font title 24 mobile / 26 wide.
          - Feature flags gestiti a runtime: EXPLAINABILITY_ENABLED (probe su /explanation, fallback silenzioso), ACTION_CENTER_ENABLED (probe su /history), DAILY_SUMMARY_ENABLED.
          - I supporting files nuovi: /app/frontend/src/components/Skeleton.tsx, /app/frontend/src/utils/haptic.ts, /app/frontend/src/hooks/use-online-status.ts. tokens.ts esteso. labels.ts esteso con formatRelativeAgo.
          Screenshot manuali OK: home mobile, "Perché adesso?" sheet, Rimanda sheet, home desktop. Nessun errore compile.

test_plan_iter12:
  current_focus:
    - "Login demo@ora.app / Demo!2026 → tab Home renderizza Focus Now"
    - "FocusNowCard: mostra title, description, human_summary, meta (Durata/Impatto/Rimando/Confidenza), score/deadline se presenti"
    - "Pulsante 'Perché adesso?' apre sheet con regole tradotte in italiano (labels.ts), passi di ragionamento, stime, data_sources, context_used"
    - "Action Center: Inizia → status diventa 'In corso' + progress bar info. Risolvi → ConfirmSheet → completa (rimossa da attive). Parziale → PartialSheet (25/50/75%) + nota → status 'Parziale' con bar warning. Rimanda → PostponeSheet 3 opzioni + reason. Altro → MoreMenu (Blocca/Ignora/Cronologia)."
    - "Blocca → ReasonSheet richiede motivo (obbligatorio). Ignora → ReasonSheet opzionale."
    - "Cronologia → HistorySheet mostra timeline azioni con labels tradotti (USER_ACTION_LABELS)"
    - "Daily card 'La tua giornata': score pill colorato, meta chips, warnings/opportunities chips con colori semantici, 'Vedi giornata' → DailyDetailSheet con busy/free slots + signals"
    - "Later ('Dopo') cards con indice, meta, mini 'Perché?' che apre WhyNowSheet dedicato"
    - "Empty states: nessuna decision → EmptyFocus. Calendar non collegato → 'Collega Google Calendar'. Calendar collegato ma non synced → 'Avvia sincronizzazione'."
    - "Pull-to-refresh aggiorna dati senza mostrare skeleton (silent reload)"
    - "Offline: nessuna connessione → banner 'Sei offline' + header status 'Offline'. Riconnessione → 'Aggiornato ora'."
    - "Errori server: 403 → 'Permesso non concesso', 404 → 'non più disponibile', 409 → 'transizione non consentita', 5xx → 'servizio non disponibile'"
    - "Feature flag degradation: se /explanation risponde 404 con detail 'abilitata', il pulsante 'Perché?' scompare; se /history è disattivato, action center resta ma history mostra fallback."
    - "Accessibilità: touch target ≥44px, screen reader legge 'Focus adesso', 'Stato Da fare', 'Perché è prioritaria', ecc."
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication_iter12:
  - agent: "main"
    message: |
      Iterazione 12 frontend pronta per validazione. Backend invariato al 100% (nessuna modifica).
      Credenziali test: demo@ora.app / Demo!2026 (o /api/auth/register se non esiste).
      URL: preview web (localhost:3000). Testing agent deve validare FRONTEND ONLY.
      Note importanti:
      - I test devono attendere caricamento (skeleton visibili) e poi verificare che il contenuto compaia con animazione.
      - Non modificare direttamente lo stato via DB o via chiamate API dirette: il test deve avvenire tramite UI (login → home → interazione).
      - Il backend usa CALENDAR_PROVIDER_MODE=fake di default; alcune Decision seed dovrebbero essere presenti dopo il register/login.
      - Feature flags backend attivi di default; il fallback UI si verifica solo se disattivati manualmente.

