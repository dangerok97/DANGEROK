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
