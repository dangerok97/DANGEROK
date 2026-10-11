"""Real disposable Mongo tests, using the existing isolated fixtures."""
import json
import pytest
from test_catalog import database, api_module
from vision_catalog import CatalogService, Manifest, MODELS, VERSIONS, JOBS, seeds
from vision_seed_library import common_recipes, METADATA, canonical_key, recognition_hint


def test_pack_has_twenty_new_original_families_and_124_total_parts():
    items = seeds()
    assert len(items) == 25
    assert len(common_recipes()) == 20
    assert len({x.canonical_key for x in items}) == 25
    assert sum(len(x.parts) for x in items) == 124
    assert all(x.canonical_key in METADATA for x in items)
    assert all(x.evidence_level == 'illustrative' for x in items)


@pytest.mark.parametrize('row', common_recipes(), ids=lambda r: r['key'])
def test_new_recipes_are_bounded_separable_and_have_explanations(row):
    manifest = Manifest.model_validate(row['manifest'])
    assert 3 <= len(manifest.parts) <= 8
    assert len({p.exploded for p in manifest.parts}) == len(manifest.parts)
    assert len({p.key for p in manifest.parts}) == len(manifest.parts)
    assert all(p.function and p.how_it_works for p in manifest.parts)
    assert all(p.evidence == 'typical' for p in manifest.parts)
    assert row['key'] in recognition_hint()
    assert row['aliases'] and row['category']


@pytest.mark.parametrize('alias,expected', [('USB stick','usb_flash_drive'),('TASTIERA','computer_keyboard'),
    ('telefono cellulare','smartphone'),('Portamine','mechanical_pencil'),('cucitrice','stapler'),
    ('borraccia termica','insulated_bottle'),('penna con cappuccio','capped_pen'),
    ('wireless earbuds','wireless_earbud'),('mouse','computer_mouse')])
def test_known_aliases_are_canonical(alias, expected):
    assert canonical_key(alias) == expected


def test_ambiguous_and_incompatible_families_are_not_silently_merged():
    for value in ['notebook', 'mechanical_keyboard', 'wired_earphones', 'aerosol_can', 'water_flask']:
        assert canonical_key(value) == value
    assert canonical_key('capped_pen') != canonical_key('click_pen')
    assert canonical_key(None) == ''


@pytest.mark.asyncio
async def test_alias_reuses_persisted_seed_without_generation(database):
    service = CatalogService(database)
    async def forbidden(): raise AssertionError('Known seed must not invoke the generator')
    result = await service.resolve(key='usb_stick', title='', user_id='alice', generator=forbidden)
    assert result['cache_hit'] and not result['generation_used']
    assert result['manifest']['canonical_key'] == 'usb_flash_drive'
    assert await database[JOBS].count_documents({}) == 0
    other = await CatalogService(database).find('thumb_drive', 'bob')
    assert other['version_id'] == result['version_id']


@pytest.mark.asyncio
async def test_catalog_has_categories_and_new_counts(database):
    rows = await CatalogService(database).list_models('alice')
    assert len(rows) == 25
    phone = next(r for r in rows if r['canonical_key'] == 'smartphone')
    assert phone['category'] == 'Elettronica' and phone['shared']
    assert 'telefono_cellulare' in phone['aliases']
    assert all(row['source_type'] == 'seed' for row in rows)


@pytest.mark.asyncio
async def test_seed_upgrade_preserves_old_version_and_private_record(database):
    service = CatalogService(database)
    candidate = seeds()[1].model_dump(mode='json')
    candidate['canonical_key'] = 'stapler'; candidate['title'] = 'Vecchio schema generato'
    manifest = Manifest.model_validate(candidate)
    old = await service._store(manifest, 'shared', 'generated')
    private = await service._store(manifest, service.private_scope('alice'), 'generated')
    await service.initialize()
    shared = await service.find('stapler', 'bob')
    assert shared['source_type'] == 'seed'
    assert shared['version_id'] != old['version_id']
    assert await database[VERSIONS].find_one({'_id': old['version_id']})
    assert (await service.find('stapler','alice'))['version_id'] == private['version_id']
    await CatalogService(database).initialize()
    assert (await service.find('stapler','bob'))['version_id'] == shared['version_id']
    assert await database[MODELS].count_documents({'canonical_key':'stapler','scope':'shared'}) == 1


@pytest.mark.asyncio
async def test_new_seed_does_not_resurrect_retired_generated_head(database):
    service = CatalogService(database)
    manifest = Manifest.model_validate(common_recipes()[0]['manifest'])
    old = await service._store(manifest,'shared','generated')
    await database[MODELS].update_one({'_id': old['model_id']}, {'$set': {'status':'retired'}})
    await service.initialize()
    assert await service.find('smartphone','alice') is None


@pytest.mark.asyncio
async def test_recognizer_uses_canonical_family_without_claiming_exact_hardware(api_module):
    raw = dict(recognized=True, canonical_key='mobile_phone', object_name='Telefono',
               confidence='high', bbox=[100,200,900,800], safe_to_generate=True)
    value = api_module.normalize_identification(raw)
    assert value['canonical_key'] == 'smartphone'
    assert 'computer_keyboard' in api_module.IDENTIFY
    assert 'membrana' in api_module.IDENTIFY
