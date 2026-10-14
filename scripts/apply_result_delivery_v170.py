"""Temporary exact-source integration; removed before merging the candidate."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[1]
FENCES = {
 'backend/delivery/models.py': '78ad07ced9b9989faeb065ac6f70fa3a5bd63953',
 'backend/delivery/service.py': '0a7ea64e27c501593dcbeaa10b3e46248aedc256',
 'backend/delivery/admission.py': '150961f798dba9c882fe261ecd10b6bba7cdb8f3',
 'backend/connected/core_work.py': '4c710d9b2ca6a6047d789a05ef746eb7d164f311',
}
for path, expected in FENCES.items():
 raw = (ROOT/path).read_bytes()
 actual = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
 if actual != expected: raise RuntimeError('source_sha_conflict:'+path)


def patch(path, edits):
 file = ROOT/path; source = file.read_text()
 for before, after in edits:
  if source.count(before) != 1: raise RuntimeError('unique_anchor_missing:'+path+':'+before[:90])
  source = source.replace(before, after)
 compile(source,path,'exec');file.write_text(source)


patch('backend/delivery/models.py', [
 ('DeliverySource = Literal["opportunity", "agent_need"]',
  'DeliverySource = Literal["opportunity", "agent_need", "source_result"]'),
])

patch('backend/delivery/service.py', [
 ('        subject_id = getattr(subject, "id", "")\n        if kind == "agent_need":',
  '''        subject_id = getattr(subject, "id", "")
        if kind == "source_result":
            from delivery.source_results import current_subject, existing_plan, settled_or_inflight
            try:
                subject = await current_subject(self.db, user_id, subject_id)
            except MemorySourcesUnavailable:
                return await self._source_check_unavailable(user_id, kind, subject_id)
            if subject is None:
                await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                             reason="il risultato verificato non è più attuale")
                return DeliveryResult(blocked_by="source_result_changed")
            previous = await existing_plan(self.db, user_id, subject_id)
            if settled_or_inflight(previous):
                return DeliveryResult(mode="in_app", blocked_by="source_result_already_handled",
                                      plan=DeliveryPlan.model_validate(previous))
            import os
            if not os.environ.get("ORA_SOURCE_MODEL_CONTRACT"):
                return DeliveryResult(unavailable=True, blocked_by="source_model_contract_required")
        if kind == "agent_need":'''),
 ('        answer = await decide_delivery(moment, language=language)',
  '''        # Source-origin work and its communication use the same configured
        # provider/model boundary; ordinary notification decisions are unchanged.
        if kind == "source_result":
            from llm.model_contract import scoped_model_contract
            with scoped_model_contract(os.environ.get("ORA_SOURCE_MODEL_CONTRACT")):
                answer = await decide_delivery(moment, language=language)
        else:
            answer = await decide_delivery(moment, language=language)'''),
 ('        decision = self._read(answer)\n',
  '''        if kind == "source_result":
            try:
                subject = await current_subject(self.db, user_id, subject_id)
            except MemorySourcesUnavailable:
                return await self._source_check_unavailable(user_id, kind, subject_id)
            if subject is None:
                await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                             reason="il risultato è cambiato durante la decisione")
                return DeliveryResult(blocked_by="source_result_changed")
        decision = self._read(answer)
'''),
 ('        kind = source_of(subject)\n        existing = await self.repo.open_plan_for(',
  '''        kind = source_of(subject)
        if kind == "source_result":
            from delivery.source_results import save_decision
            return await save_decision(self, subject, decision)
        existing = await self.repo.open_plan_for('''),
 ('    ) -> DeliveryPlan:\n        existing = await self.repo.open_plan_for(\n            user_id, subject_id, source_type=source_type',
  '''    ) -> DeliveryPlan:
        if source_type == "source_result":
            from delivery.source_results import current_subject, save_decision
            subject = await current_subject(self.db, user_id, subject_id)
            if subject is None:
                raise MemorySourcesUnavailable("source_result_changed_before_hold")
            return await save_decision(self, subject, decision, held_reason=why)
        existing = await self.repo.open_plan_for(
            user_id, subject_id, source_type=source_type'''),
 ('        if plan.owner_id != user_id:\n            return None\n        if plan.source_type == "opportunity":',
  '''        if plan.owner_id != user_id:
            return None
        if plan.source_type == "source_result":
            from delivery.source_results import current_subject
            return await current_subject(self.db, user_id, plan.source_id)
        if plan.source_type == "opportunity":'''),
 ('    async def _send(self, user_id: str, plan: DeliveryPlan) -> None:\n        from delivery.provider import get_provider',
  '''    async def _send(self, user_id: str, plan: DeliveryPlan) -> None:
        if plan.source_type == "source_result":
            from delivery.source_results import send_guarded
            await send_guarded(self, user_id, plan)
            return
        await self._send_current(user_id, plan)

    async def _send_current(self, user_id: str, plan: DeliveryPlan):
        from delivery.provider import get_provider'''),
 ('                        "push retry wake deferred: %s", type(exc).__name__\n                    )\n            return\n',
  '                        "push retry wake deferred: %s", type(exc).__name__\n                    )\n            return outcome\n'),
 ('        await self.repo.save_plan(plan)\n\n    async def _defer_source_check',
  '        await self.repo.save_plan(plan)\n        return outcome\n\n    async def _defer_source_check'),
 ('    if plan.source_type == "agent_need":\n        match = re.fullmatch(',
  '''    if plan.source_type == "source_result":
        from delivery.source_results import plan_id
        if (_OPAQUE_ID.fullmatch(plan.source_id) and plan.deep_link == "/"
                and plan.id == plan_id(plan.owner_id, plan.source_id)):
            return "/"
        return None

    if plan.source_type == "agent_need":
        match = re.fullmatch('''),
])

patch('backend/delivery/admission.py', [
 ('    handled = await drain(db)\n',
  '''    handled = await drain(db)
    # Already-verified source work enters the existing delivery review pass.
    # No new scheduler or direct provider call; default pilot enrolment is empty.
    try:
        from delivery.source_result_review import drain as drain_source_results
        handled += await drain_source_results(db)
    except Exception as exc:
        logger.info("verified source result review deferred: %s", type(exc).__name__)
'''),
])

patch('backend/connected/core_work.py', [
 ('                \'_core_work.home_pending\': False, \'_core_work.home_activity_id\': activity_id,\n',
  '''                '_core_work.home_pending': False, '_core_work.home_activity_id': activity_id,
                '_core_work.delivery_review': {'phase': 'pending', 'due_at': _now().isoformat(), 'attempts': 0},
'''),
])
print('SOURCE_RESULT_DELIVERY_HOOKS_INSTALLED')
