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

