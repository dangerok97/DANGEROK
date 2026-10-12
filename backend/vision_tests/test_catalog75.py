"""Real Mongo fixtures; synthetic identities only. No production state or provider calls."""
import hashlib
import json
from pathlib import Path

import pytest
from test_catalog import database, api_module
from vision_catalog import CatalogService, Manifest, MODELS, VERSIONS, JOBS, seeds
from vision_seed_library import METADATA, PACK_VERSION, all_recipes, canonical_key, recognition_hint
from vision_catalog_extended import EXPECTED_ADDITIONS

BASELINE = json.loads((Path(__file__).parent / 'fixtures' / 'legacy25_sha256.json').read_text())
ALL = seeds()
ADDED = [model for model in ALL if model.canonical_key not in BASELINE]


def fingerprint(model):
    body = json.dumps(model.model_dump(mode='json'), ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(body.encode()).hexdigest()


def test_exactly_75_families_without_counting_aliases_or_versions():
    assert EXPECTED_ADDITIONS == 50
    assert len(ALL) == len({m.canonical_key for m in ALL}) == 75
    assert len(ADDED) == 50
    assert len(all_recipes()) == 70
    assert len(METADATA) == 75
    assert PACK_VERSION == 'common-75-v1'
    assert set(BASELINE).issubset({m.canonical_key for m in ALL})


def test_original_25_manifests_remain_byte_equivalent_canonically():
    previous = {m.canonical_key: fingerprint(m) for m in ALL if m.canonical_key in BASELINE}
    assert len(previous) == 25
    assert previous == BASELINE  # Existing immutable catalog version IDs must not change.


@pytest.mark.parametrize('model', ADDED, ids=lambda m: m.canonical_key)
def test_added_family_has_specific_bounded_explorable_groups(model):
    assert Manifest.model_validate(model.model_dump()) == model
    assert 3 <= len(model.parts) <= 8
    assert model.evidence_level == 'illustrative' and model.match_scope == 'family'
    assert len({p.name for p in model.parts}) == len(model.parts)
    assert len({p.key for p in model.parts}) == len(model.parts)
    assert len({p.exploded for p in model.parts}) == len(model.parts)
    assert any(p.assembled != p.exploded for p in model.parts)
    assert all(len(p.function) >= 15 and len(p.how_it_works) >= 35 for p in model.parts)
    assert all(p.evidence == 'typical' for p in model.parts)
    meta = METADATA[model.canonical_key]
    assert meta['title'] == model.title and meta['aliases'] and meta['category']
    assert canonical_key(model.title) == model.canonical_key
    for alias in meta['aliases']:
        assert canonical_key(alias) == model.canonical_key
    assert model.canonical_key in recognition_hint()


def test_recipes_are_not_duplicate_geometries_with_relabelled_names():
    signatures = []
    for model in ADDED:
        geometry = [(p.shape, p.size, p.assembled, p.exploded) for p in model.parts]
        signatures.append(json.dumps(geometry))
    assert len(signatures) == len(set(signatures)) == 50
    assert len({m.title for m in ALL}) == 75


def test_references_are_scoped_https_not_private_media():
    for key in {m.canonical_key for m in ADDED}:
        refs = METADATA[key]['sources']
        assert len(refs) == len({r['url'] for r in refs})
        for source in refs:
            assert source['url'].startswith('https://') and source['title']
            assert 'image_base64' not in source['url']
            assert 'api_key' not in source['url'].lower()


@pytest.mark.parametrize('alias,key', [
    ('moka','moka_pot'), ('MACINACAFFÈ MANUALE','manual_coffee_grinder'),
    ('cerniera lampo','zipper'), ('cerniera porta','door_hinge'),
    ('mulinello','spinning_reel'), ('cassa bluetooth','portable_speaker'),
    ('binocolo','binoculars'), ('powerbank','power_bank'),
    ('campanello bici','bicycle_bell'), ('fischietto','sports_whistle'),
])
def test_new_aliases_share_one_canonical_model(alias,key):
    assert canonical_key(alias) == key


def test_incompatible_variants_stay_distinct():
    assert canonical_key('moka') != canonical_key('french_press')
    assert canonical_key('door_hinge') != canonical_key('zipper')
    assert canonical_key('manual_coffee_grinder') != canonical_key('electric_coffee_grinder')
    assert canonical_key('wireless_earbud') != canonical_key('overear_headphones')
    assert canonical_key('bottle') != canonical_key('oil_dispenser')


@pytest.mark.asyncio
async def test_all_added_families_reused_by_a_new_user_without_generation(database):
    a = CatalogService(database)
    async def forbidden():
        raise AssertionError('A curated family must not call AI generation')
    for model in ADDED:
        alias = METADATA[model.canonical_key]['aliases'][0]
        first = await a.resolve(key=alias,title='',user_id='alice',generator=forbidden)
        second = await CatalogService(database).find(model.canonical_key,'bob')
        assert first['status'] == 'family' and first['cache_hit'] and not first['generation_used']
        assert first['version_id'] == second['version_id']
        assert first['source_type'] == 'seed' and first['shared']
    assert await database[MODELS].count_documents({}) == 75
    assert await database[VERSIONS].count_documents({}) == 75
    assert await database[JOBS].count_documents({}) == 0
    await CatalogService(database).initialize()
    assert await database[VERSIONS].count_documents({}) == 75


@pytest.mark.asyncio
async def test_expansion_adds_fifty_to_preexisting_twentyfive_without_replacing_them(database):
    previous = CatalogService(database)
    for model in ALL:
        if model.canonical_key in BASELINE:
            await previous.install_seed(model)
    old = {m['canonical_key']: m['current_version'] for m in await database[MODELS].find({}).to_list(100)}
    assert len(old) == 25
    await CatalogService(database).initialize()
    current = {m['canonical_key']:m['current_version'] for m in await database[MODELS].find({}).to_list(100)}
    assert len(current) == 75 and {key: current[key] for key in old} == old


@pytest.mark.asyncio
async def test_new_family_promotion_keeps_old_generated_version_and_private_head(database):
    service = CatalogService(database)
    candidate = ADDED[0].model_dump(mode='json'); candidate['title'] = 'Older generic candidate'
    old = await service._store(Manifest.model_validate(candidate),'shared','generated')
    private = await service._store(Manifest.model_validate(candidate),service.private_scope('alice'),'generated')
    await service.initialize()
    shared = await service.find(candidate['canonical_key'],'bob')
    assert shared['source_type'] == 'seed' and shared['version_id'] != old['version_id']
    assert await database[VERSIONS].find_one({'_id':old['version_id']})
    assert (await service.find(candidate['canonical_key'],'alice'))['version_id'] == private['version_id']


@pytest.mark.asyncio
async def test_withdrawn_new_family_does_not_get_resurrected(database):
    service = CatalogService(database)
    old = await service._store(ADDED[0],'shared','generated')
    await database[MODELS].update_one({'_id':old['model_id']},{'$set':{'status':'retired'}})
    await service.initialize()
    assert await service.find(ADDED[0].canonical_key,'bob') is None
    assert len(await service.list_models('bob')) == 74


@pytest.mark.asyncio
async def test_recognition_prompt_includes_new_families_without_exact_model_claim(api_module):
    assert 'manual_coffee_grinder' in api_module.IDENTIFY
    assert 'spinning_reel' in api_module.IDENTIFY
    for model in ADDED:
        assert model.canonical_key in api_module.IDENTIFY
    raw = dict(recognized=True, canonical_key='mulinello', object_name='Mulinello',
               confidence='high', bbox=[100,200,900,800], safe_to_generate=True)
    assert api_module.normalize_identification(raw)['canonical_key'] == 'spinning_reel'
