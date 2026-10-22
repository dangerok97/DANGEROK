"""Synthetic persistence: owner isolation, duplicate protection and revisions."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from pymongo.errors import DuplicateKeyError
from recipes.service import RecipeError, RecipeService, RecipeWrite


class Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, field, direction):
        self.docs.sort(key=lambda d: d[field], reverse=direction == -1)
        return self
    def limit(self, n):
        self.docs = self.docs[:n]
        return self
    async def to_list(self, length): return deepcopy(self.docs[:length])


class Collection:
    def __init__(self): self.docs = {}
    async def find_one(self, q):
        item = self.docs.get(q['_id'])
        return deepcopy(item) if item and all(item.get(k) == v for k, v in q.items()) else None
    async def count_documents(self, q):
        return sum(all(d.get(k) == v for k, v in q.items()) for d in self.docs.values())
    async def insert_one(self, doc):
        if doc['_id'] in self.docs: raise DuplicateKeyError('duplicate')
        self.docs[doc['_id']] = deepcopy(doc)
    def find(self, q):
        return Cursor([deepcopy(d) for d in self.docs.values()
                       if all(d.get(k) == v for k, v in q.items())])
    async def update_one(self, q, changes):
        item = self.docs.get(q['_id'])
        if not item or not all(item.get(k) == v for k, v in q.items()):
            return SimpleNamespace(matched_count=0)
        item.update(deepcopy(changes['$set']))
        return SimpleNamespace(matched_count=1)
    async def delete_one(self, q):
        item = self.docs.get(q['_id'])
        if item and all(item.get(k) == v for k, v in q.items()):
            del self.docs[q['_id']]
            return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


@pytest.mark.asyncio
async def test_save_duplicate_edit_and_delete():
    svc = RecipeService(SimpleNamespace(ora_recipes=Collection()))
    body = RecipeWrite(title='Zucchine', source_url='https://example.org/recipe')
    saved, created = await svc.create('owner1', body)
    assert created and saved['revision'] == 1
    same, created = await svc.create('owner1', body)
    assert not created and saved['id'] == same['id']
    assert len(await svc.list('owner1')) == 1
    assert len(await svc.list('owner2')) == 0
    with pytest.raises(RecipeError):
        await svc.update('owner2', saved['id'], RecipeWrite(
            title='Wrong owner', source_url=body.source_url, revision=1))
    changed = await svc.update('owner1', saved['id'], RecipeWrite(
        title='Zucchine', source_url=body.source_url, ingredients=['2 zucchine'],
        steps=['Taglia le zucchine'], revision=1, favorite=True))
    assert changed['revision'] == 2 and changed['favorite']
    with pytest.raises(RecipeError):
        await svc.update('owner1', saved['id'], RecipeWrite(
            title='Outdated', source_url=body.source_url, revision=1))
    with pytest.raises(RecipeError):
        await svc.delete('owner1', saved['id'], revision=1)
    await svc.delete('owner1', saved['id'], revision=2)
    assert await svc.list('owner1') == []


@pytest.mark.asyncio
async def test_identical_link_is_separate_per_account():
    svc = RecipeService(SimpleNamespace(ora_recipes=Collection()))
    recipe = RecipeWrite(title='Torta', source_url='https://example.org/torta')
    a, _ = await svc.create('ownerA', recipe)
    b, _ = await svc.create('ownerB', recipe)
    assert a['id'] != b['id']
    assert (await svc.list('ownerA'))[0]['id'] == a['id']
    assert (await svc.list('ownerB'))[0]['id'] == b['id']
