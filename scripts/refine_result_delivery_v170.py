"""Second exact-blob integration step, removed with the temporary writer."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[1]
FENCES = {
 'backend/delivery/service.py': 'dffbcc0d60cdf04b6478533c6adbc9cd3f5758af',
 'backend/connected/core_work.py': 'b7215ecc35a3647f7c60c04c65147e0c1a7f93f3',
 'backend/delivery/source_results.py': '2b44475fc71e0f8005b003985477ca2bf8c09846',
 'backend/tests/test_delivery_v38.py': '5b099731207870eefad3ba6999df2b94ab8913c6',
}
for path, expected in FENCES.items():
 b=(ROOT/path).read_bytes()
 if hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()!=expected:
  raise RuntimeError('source_sha_conflict:'+path)


def patch(path, edits):
 p=ROOT/path;s=p.read_text()
 for before,after in edits:
  if s.count(before)!=1:raise RuntimeError('anchor_conflict:'+path+':'+before[:80])
  s=s.replace(before,after)
 compile(s,path,'exec');p.write_text(s)


patch('backend/delivery/service.py', [
 ('''        if kind == "source_result":
            from llm.model_contract import scoped_model_contract
            with scoped_model_contract(os.environ.get("ORA_SOURCE_MODEL_CONTRACT")):
                answer = await decide_delivery(moment, language=language)
        else:
            answer = await decide_delivery(moment, language=language)''',
  '''        from contextlib import nullcontext
        contract_scope = nullcontext()
        if kind == "source_result":
            from llm.model_contract import scoped_model_contract
            contract_scope = scoped_model_contract(os.environ.get("ORA_SOURCE_MODEL_CONTRACT"))
        with contract_scope:
            answer = await decide_delivery(moment, language=language)'''),
])

SUMMARY = '''def _home_summary(node, operation):
    """One factual formatter shared by Home and subsequent receipt delivery."""
    attrs = node['attributes']
    moment = datetime.fromisoformat(attrs['starts_at'].replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('result_event_timezone_missing')
    moment = moment.astimezone(ZoneInfo(attrs.get('timezone') or 'Europe/Rome'))
    verbs = {'created': 'Ho aggiunto', 'already_created': 'È già presente',
             'updated': 'Ho aggiornato', 'already_updated': 'È già aggiornato'}
    verb = verbs.get(operation)
    if verb is None:
        raise ValueError('unsupported_verified_operation')
    return (f'{verb} nel calendario ORA «{node["label"][:95]}»: '
            f'{moment:%d/%m/%Y} alle {moment:%H:%M}.')


'''
patch('backend/connected/core_work.py', [
 ('def _due_query(owner_id):', SUMMARY+'def _due_query(owner_id):'),
 ('''            attrs = node['attributes']
            moment = datetime.fromisoformat(attrs['starts_at'].replace('Z', '+00:00'))
            moment = moment.astimezone(ZoneInfo(attrs.get('timezone') or 'Europe/Rome'))
            operation = effect['observation']['payload'].get('operation')
            verbs = {'created': 'Ho aggiunto', 'already_created': 'È già presente',
                     'updated': 'Ho aggiornato', 'already_updated': 'È già aggiornato'}
            verb = verbs.get(operation)
            if verb is None:
                raise ValueError('unsupported_verified_operation')
            summary = (f'{verb} nel calendario ORA «{node["label"][:95]}»: '
                       f'{moment:%d/%m/%Y} alle {moment:%H:%M}.')''',
  '''            summary = _home_summary(node, effect['observation']['payload'].get('operation'))'''),
])

patch('backend/delivery/source_results.py', [
 ('    from connected.core_work import _event_version\n',
  '    from connected.core_work import _event_version, _home_summary\n'),
 ("    if not activity or not activity.get('summary'):\n        return None\n",
  "    if not activity or activity.get('summary') != _home_summary(event, payload.get('operation'))[:200]:\n        return None\n"),
 ('        not_after=min(filter(None, [decision.not_after, subject.valid_until])),',
  '        not_after=min(moment(value) for value in (decision.not_after, subject.valid_until) if value).isoformat(),'),
 ("        plan.transport_retry_alarm_queued = existing.get('transport_retry_alarm_queued', False)\n",
  "        plan.transport_retry_alarm_queued = existing.get('transport_retry_alarm_queued', False)\n        if plan.transport_retry_due and moment(plan.transport_retry_due) > now():\n            plan.not_before = max(moment(plan.not_before or now().isoformat()), moment(plan.transport_retry_due)).isoformat()\n            plan.status = 'held'\n"),
])

patch('backend/tests/test_delivery_v38.py', [
 ('class FakeModel:\n',
  '''@pytest.fixture(autouse=True)
def _restore_legacy_permission_reader():
    # _allow_push predates monkeypatch usage and assigns a module attribute.
    # Its synthetic permission must not leak into later account/channel tests.
    from delivery import context
    original = context._permission
    try:
        yield
    finally:
        context._permission = original


class FakeModel:
'''),
 ('''            # The origin is preserved: a thread opened by an interruption is
            # not the same as one somebody chose to open.
            assert "entry=notification" in plan.deep_link''',
  '''            # Attribution is carried by the owned plan. The canonical
            # opportunity route no longer uses the old conversation query.
            assert plan.source_type == "opportunity" and plan.source_id == opportunity.id
            opened = await DeliveryService(db).record_outcome(uid, plan.id, "opened")
            assert opened["ok"] and opened["route"] == plan.deep_link'''),
])
print('SOURCE_RESULT_COPY_AND_JUDGEMENT_REFINED')
