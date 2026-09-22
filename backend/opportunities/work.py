"""Durable, owner-scoped entry into existing ORA work from an update card."""
from datetime import datetime, timezone
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError


def evidence_labels(evidence):
    # Repeated references are not independent confirmations.
    unique = {(e.kind, e.ref): e for e in evidence}
    return list(dict.fromkeys(e.summary or e.kind for e in unique.values()))


async def update_work(db, owner, opportunity, *, start=False, reply='', source_kind='opportunity'):
    key = {'_id': f'{owner}:{opportunity.id}', 'owner_id': owner}
    source_col = db.opportunities if source_kind == 'opportunity' else db.proactive_suggestions
    source_key = {'owner_id' if source_kind == 'opportunity' else 'user_id': owner, 'id': opportunity.id}
    col = db.update_work
    row = await col.find_one(key)
    if not start:
        if row and row.get('session_id') and row.get('status') in ('ready', 'needs_user'):
            from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
            latest = await AICoreOrchestrator(db).get(owner, row['session_id'])
            if latest.get('ok') and latest.get('ora_text') != (row.get('result') or {}).get('ora_text'):
                row = {**row, 'result': latest, 'status': 'ready'}
                await col.update_one(key, {'$set': {'result': latest, 'status': 'ready'}})
                await source_col.update_one(source_key, {'$set': {'work_status': 'ready'}})
        if row and row.get('status') == 'running':
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(row['started_at'])).total_seconds()
            if age > 180:
                row = {**row, 'status': 'interrupted', 'message': 'La verifica non ha restituito un esito. Non la avvio di nuovo automaticamente.'}
        return {k: v for k, v in (row or {'status': 'not_started'}).items() if k not in ('_id', 'owner_id')}
    if row and not reply:
        return await update_work(db, owner, opportunity, source_kind=source_kind)
    if reply:
        if not row or not row.get('session_id'):
            raise HTTPException(409, 'Nessuna verifica da continuare.')
        claimed = await col.update_one({**key, 'status': {'$in': ['ready', 'needs_user']}}, {'$set': {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()}})
        if not claimed.modified_count:
            return await update_work(db, owner, opportunity, source_kind=source_kind)
    else:
        try:
            await col.insert_one({**key, 'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()})
        except DuplicateKeyError:
            return await update_work(db, owner, opportunity, source_kind=source_kind)
    await source_col.update_one(source_key, {'$set': {'work_status': 'running'}})
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
    orch = AICoreOrchestrator(db)
    try:
        if reply:
            result = await orch.message(owner, row['session_id'], text=reply)
        else:
            result = await orch.start(owner, origin='home', entry_point='update', opportunity_id=opportunity.id if source_kind == 'opportunity' else None,
                text='Verifica questo aggiornamento e il prossimo passo proposto usando le fonti accessibili. '
                     'Tratta la segnalazione come ipotesi da verificare, non come fatto confermato. '
                     'Riferimenti ripetuti non provano eventi ripetuti. Distingui fonti consultate, risultati e limiti. '
                     'Non effettuare modifiche o invii: per quelle azioni prepara una proposta da autorizzare. '
                     'Se manca un dato, fai una domanda specifica.\nSegnalazione: '+opportunity.semantic_summary+
                     '\nPasso proposto: '+(opportunity.what_ora_can_do or '')+
                     '\nRiferimenti: '+'; '.join(evidence_labels(opportunity.evidence)))
        status = 'needs_user' if result.get('question') else 'ready'
        if not result.get('ok'):
            status = 'failed'
        await source_col.update_one(source_key, {'$set': {'work_status': status}})
        await col.update_one(key, {'$set': {'status': status, 'session_id': result.get('session_id'), 'result': result,
            'updated_at': datetime.now(timezone.utc).isoformat()}})
    except Exception:
        await source_col.update_one(source_key, {'$set': {'work_status': 'failed'}})
        # Never silently launch a second execution after an uncertain failure.
        await col.update_one(key, {'$set': {'status': 'failed', 'message': 'Verifica interrotta. Non considero risolto questo aggiornamento.'}})
        raise HTTPException(503, 'Verifica interrotta. Riapri la scheda per controllare lo stato.') from None
    return await update_work(db, owner, opportunity, source_kind=source_kind)
