from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from home.models import ConnectionWarning, HomeItem
from ingestion.reading import plain, where

from ._util import now_iso, stable_id


async def google_connection_state(db, user_id: str) -> Dict[str, Any]:
    inst = await db.connector_instances.find_one(
        {
            "user_id": user_id,
            "connector_id": "calendar_google",
            "status": {"$in": ["connected", "syncing"]},
        },
        {"_id": 0},
    )
    return {
        "connected": bool(inst),
        "instance": inst,
        "last_sync_at": (inst or {}).get("last_sync_at"),
    }


async def load_google_calendar_events(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    state = await google_connection_state(db, user_id)
    if not state["connected"]:
        return [], []

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=14)
    # I calendari che questa persona ha scelto di far leggere a ORA. Vuoto
    # significa «quello principale», che e' anche il ripiego del sync: un
    # calendario tolto dalla selezione smette di essere letto, e le righe che
    # aveva lasciato non devono continuare a comparire come se niente fosse.
    chosen = set((state["instance"] or {}).get("selected_resource_ids") or [])
    # La domanda giusta e' «cosa c'e' in agenda da qui a due settimane», e
    # questa e' la query che la fa.
    #
    #     LA HOME NON DEVE CHIEDERE COSA E' STATO TOCCATO DI RECENTE.
    #
    # Prima chiedeva le ottanta righe piu' recentemente aggiornate e solo
    # dopo le filtrava per data. Sembra equivalente e non lo e', per due
    # motivi che si sommano.
    #
    # Il primo: ogni rilettura di un evento che non e' cambiato lascia una
    # riga `skipped` — la traccia di «l'ho guardato, e' uguale». Sono righe
    # oneste, ma non sono impegni: su questo account un solo compleanno
    # ricorrente ne aveva undici.
    #
    # Il secondo: quelle righe hanno `source_updated_at` recentissimo, quindi
    # occupano loro le ottanta posizioni. Il risultato misurato qui era che
    # la Home vedeva 2 dei 16 impegni realmente presenti nei quattordici
    # giorni successivi. Non «in ritardo»: proprio assenti, senza un errore
    # da nessuna parte — e sopra un calendario pieno la Home diceva che non
    # c'era niente.
    #
    # Quindi: si filtra per quando comincia l'impegno, si ordina per quando
    # comincia, e le righe che dicono solo «riletto, uguale» restano fuori.
    since = (now - timedelta(days=1)).isoformat()
    until = (window_end + timedelta(days=1)).isoformat()
    cur = db.ingestion_events.find(
        {
            "user_id": user_id,
            "connector_id": "calendar_google",
            "ingestion_status": {
                "$nin": ["superseded", "quarantined", "skipped"],
            },
            "source_record_type": {"$in": ["event", "calendar_event", "google_event"]},
            where("starts_at"): {"$gte": since, "$lte": until},
        },
        {"_id": 0},
    ).sort(where("starts_at"), 1).limit(200)
    docs = await cur.to_list(200)

    # Uno stesso evento puo' comunque avere piu' di una riga viva — una
    # rilettura che ha davvero visto un cambiamento ne aggiunge una. Vale la
    # piu' recente: due carte per lo stesso appuntamento sono un secondo
    # appuntamento, per chi guarda.
    newest: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        key = str(d.get("external_id") or d.get("id") or "")
        seen_before = newest.get(key)
        if seen_before is None or str(d.get("ingested_at") or "") > str(
            seen_before.get("ingested_at") or ""
        ):
            newest[key] = d
    docs = list(newest.values())

    items: List[HomeItem] = []
    for d in docs:
        # La busta viene tolta qui, una volta.
        #
        # Senza questa riga `starts_at` e' un dizionario: verita' per il
        # controllo `if not start` qui sotto, impossibile da leggere per
        # `fromisoformat`, e quindi ogni evento vero finiva nell'`except` e
        # spariva in silenzio. La Home diceva «nessun impegno» sopra un
        # calendario pieno, e nessun errore lo raccontava da nessuna parte.
        payload = plain(d.get("normalized_payload"))
        if chosen and str(payload.get("calendar_id") or "") not in chosen:
            continue
        if str(payload.get("status") or "").lower() == "cancelled":
            # Cancellato su Google. La riga resta — e' la traccia di una cosa
            # che c'e' stata — ma un impegno annullato non e' un impegno, e
            # mostrarlo lo rende un appuntamento a cui qualcuno si presenta.
            continue
        start = payload.get("starts_at") or payload.get("start") or payload.get("start_datetime")
        end = payload.get("ends_at") or payload.get("end") or payload.get("end_datetime")
        title = payload.get("title") or payload.get("summary") or "Evento calendario"
        if not start:
            continue
        try:
            st = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            if st < now - timedelta(hours=2) or st > window_end:
                continue
        except Exception:
            continue
        loc = payload.get("location")
        eid = d.get("id") or d.get("external_id") or title
        ext = payload.get("extendedProperties") or payload.get("extended_properties") or {}
        priv = (ext.get("private") or {}) if isinstance(ext, dict) else {}
        items.append(HomeItem(
            id=stable_id("gcal", user_id, str(eid)),
            type="event",
            subtype="google_calendar",
            title=title,
            description=payload.get("description"),
            source_type="google_calendar",
            source_id=str(eid),
            start_at=str(start),
            end_at=str(end) if end else None,
            location=loc,
            status="open",
            confidence=0.9,
            created_at=d.get("ingested_at") or now_iso(),
            updated_at=d.get("source_updated_at") or now_iso(),
            meta={
                "dedupe_key": f"gcal:{eid}",
                "external_id": d.get("external_id"),
                "ora_event_id": priv.get("ora_event_id") or payload.get("ora_event_id"),
                "ora_goal_id": priv.get("ora_goal_id") or payload.get("ora_goal_id"),
                "goal_id": priv.get("ora_goal_id") or priv.get("goal_id") or payload.get("goal_id"),
                "study_plan_id": priv.get("ora_study_plan_id") or priv.get("study_plan_id") or payload.get("study_plan_id"),
                "travel_project_id": priv.get("ora_travel_project_id") or priv.get("travel_project_id") or payload.get("travel_project_id"),
                "ora_document_id": priv.get("ora_document_id"),
            },
        ))
    return items, []
