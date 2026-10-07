"""One-time, exact-source UI repair; no personal data or provider access."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
BASE = 'frontend/src/components/ora/'

def load(path, expected):
    p = ROOT / path
    b = p.read_bytes()
    actual = hashlib.sha1(f'blob {len(b)}\0'.encode() + b).hexdigest()
    assert actual == expected, (path, actual)
    return p, b.decode()

def replace(text, before, after):
    assert text.count(before) == 1, before[:150]
    return text.replace(before, after, 1)

p, s = load(BASE + 'OraCockpitContext.tsx', '0fe17186d8c8531b41e6eeac61fa1bb046db2f19')
s = replace(s, "import { useTemporaryMemory } from './presence/useTemporaryMemory';", "import { useTemporaryMemory } from './presence/useTemporaryMemory';\nimport type { KnowledgeStar } from './presence/knowledge';")
s = replace(s, '  onTemporaryChanged,\n}: {', '  onTemporaryChanged,\n  star,\n  standalone = false,\n  readError = false,\n}: {')
s = replace(s, '  onTemporaryChanged?: () => void;\n}) {', '''  onTemporaryChanged?: () => void;
  /** A selected map snapshot; never fall back to some other/latest star. */
  star?: KnowledgeStar | null;
  standalone?: boolean;
  readError?: boolean;
}) {''')
s = replace(s, 'useTemporaryMemory(true, refreshKey)', 'useTemporaryMemory(star === undefined, refreshKey)')
s = replace(s, '  useEffect(() => {\n    void refresh();', '  useEffect(() => {\n    if (standalone) return;\n    void refresh();')
s = replace(s, '  }, [refresh, refreshKey]);', '  }, [refresh, refreshKey, standalone]);')
s = replace(s, '  const current = temporary.stars.find(star => star.id === selectedStarId) || temporary.latest;', '''  const current = star !== undefined
    ? star
    : temporary.stars.find(item => item.id === selectedStarId) || temporary.latest;''')
s = replace(s, '      await api.dismissTemporarySituation(current.situation_id);', '''      const result = await api.dismissTemporarySituation(current.situation_id);
      if (!result.ok) throw new Error('dismiss_not_confirmed');''')
s = replace(s, '          <Text style={styles.situationStatement}>{current.statement}</Text>', '''          <Text style={styles.situationStatement}>{current.statement}</Text>
          {readError ? <Text accessibilityRole="alert" style={styles.removeError}>
            Aggiornamento non riuscito: i dati mostrati sono quelli dell'ultima lettura.
          </Text> : null}''')
s = replace(s, "          <Pressable\n            onPress={() => router.push('/situazione' as any)}", "          {!standalone ? <Pressable\n            onPress={() => router.push('/situazione' as any)}")
s = replace(s, '            <Ionicons name="arrow-forward" size={16} color={palette.label} />\n          </Pressable>', '            <Ionicons name="arrow-forward" size={16} color={palette.label} />\n          </Pressable> : null}')
s = replace(s, '            disabled={removing}', '            disabled={removing || !current.situation_id}')
s = replace(s, '      {focus ? (', '      {!standalone && focus ? (')
p.write_text(s)

p, s = load(BASE + 'presence/OraPresence.tsx', '52054c9e168b2caa06b4b1a920a77a51d1ea0cba')
s = replace(s, 'useMemo, useState', 'useMemo, useRef, useState')
s = replace(s, "import { useRouter } from 'expo-router';", "import { useRouter } from 'expo-router';\nimport { OraCockpitContext } from '../OraCockpitContext';")
s = replace(s, 'cockpitChrome = false, onSelectNode }: {', 'cockpitChrome = false, onSelectNode, initialSelectedStarId = null, onKnowledgeChanged, knowledgeError = false }: {')
s = replace(s, '  cockpitChrome?: boolean;', '''  cockpitChrome?: boolean;
  initialSelectedStarId?: string | null;
  onKnowledgeChanged?: () => void;
  knowledgeError?: boolean;''')
s = replace(s, '  // A new working turn exposes its result', '''  const appliedInitialSelection = useRef<string | null>(null);
  useEffect(() => {
    if (!initialSelectedStarId) { appliedInitialSelection.current = null; return; }
    if (appliedInitialSelection.current === initialSelectedStarId) return;
    const index = stars.findIndex(star => star.id === initialSelectedStarId);
    if (index < 0) return;
    appliedInitialSelection.current = initialSelectedStarId;
    select({ index: index + 8, id: initialSelectedStarId, area: stars[index].area, kind: stars[index].kind });
  }, [initialSelectedStarId, stars, select]);
  const refreshKnowledge = useCallback(() => {
    if (knowledge === undefined) learned.reload();
    onKnowledgeChanged?.();
  }, [knowledge === undefined, learned.reload, onKnowledgeChanged]);
  useEffect(() => {
    if (selected?.id && map && !stars.some(star => star.id === selected.id)) select(null);
  }, [map, stars, selected?.id, select]);
  // A new working turn exposes its result''')
s = replace(s, "  const fact = map?.stars.find(s => s.id === selected?.id);", '''  const fact = map?.stars.find(s => s.id === selected?.id);
  useEffect(() => {
    if (!active || !foreground || !fact?.temporary) return;
    refreshKnowledge();
    const timer = setInterval(refreshKnowledge, 15000);
    return () => clearInterval(timer);
  }, [active, foreground, fact?.id, fact?.temporary, refreshKnowledge]);''')
s = replace(s, '''      {areas || selected || info ? <View style={[styles.overlay, width < 650 && styles.overlayMobile]}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.detailContent}>
          <View style={styles.detailHead}>''', '''      {areas || selected || info ? <View style={[styles.overlay, width < 650 && styles.overlayMobile]} testID="ora-map-detail">
          <View style={[styles.detailHead, { paddingHorizontal: 16 }]}>''')
s = replace(s, "{fact ? 'Un punto della tua vita' : branch", "{fact?.temporary ? 'Memoria temporanea' : fact ? 'Un punto della tua vita' : branch")
s = replace(s, '          {areas ? <>', '''        <ScrollView keyboardShouldPersistTaps="handled" style={{ minHeight: 0, flexShrink: 1 }} contentContainerStyle={styles.detailContent} testID="ora-map-detail-scroll">
          {areas ? <>''')
s = replace(s, '          </> : fact ? <>', '''          </> : fact?.temporary ? <OraCockpitContext
            key={fact.id} star={fact} standalone readError={knowledge === undefined ? learned.error : knowledgeError}
            onTemporaryChanged={() => { refreshKnowledge(); select(null); }}
          /> : fact ? <>''')
s = replace(s, "borderRadius: 18, zIndex: 20 },", "borderRadius: 18, zIndex: 20, overflow: 'hidden' },")
p.write_text(s)

p, s = load(BASE + 'presence/OraPresence.web.tsx', '7081ded109e4c38082f7eb6b50270cd66e82ebee')
s = replace(s, "    setInspection(node?.id || highlighted?.id || null);", "    setInspection(node?.id || highlighted?.id || map?.stars.find(star => star.temporary)?.id || null);")
s = replace(s, '          {inspected ? <Text style={styles.modalStatement}>', '          {inspected && !inspected.temporary ? <Text style={styles.modalStatement}>')
s = replace(s, '            knowledge={map} spotlightId={inspection || spotlight}', '''            knowledge={map} spotlightId={inspection || spotlight}
            initialSelectedStarId={inspection} onKnowledgeChanged={learned.reload} knowledgeError={learned.error}''')
p.write_text(s)

p, s = load('frontend/e2e/mobile-conversation-v93.spec.ts', '95ab5e1ab590ac7aecd6085a7ef819776417bc5d')
s = replace(s, 'async function fixture(page: Page) {', '''async function fixture(page: Page, controls: { followup?: any; removeFails?: boolean; dismissed?: string[] } = {}) {
  let removed = false;''')
a = s.index("    else if (path.includes('knowledge-map')) json = {")
b = s.index("    else if (path.includes(sid)", a)
s = s[:a] + '''    else if (path.endsWith('/dismiss')) {
      controls.dismissed?.push(path);
      if (controls.removeFails) { await route.fulfill({ status: 503, headers, json: { detail: 'Errore di prova' } }); return; }
      removed = true;
      json = { ok: true, status: 'success' };
    }
    else if (path.includes('knowledge-map')) json = {
      stars: [
        ...(!removed ? [{ id: 'star_qa_temp', area: 'memory', branch_id: null, title: 'Memoria temporanea', semantic_kind: 'Panni stesi', icon_key: 'shirt', statement: 'Panni stesi — dati simulati per collaudo UI', status: 'known', provenance: 'Dati simulati', temporary: true, situation_id: 'sit_qa_1', follow_up: controls.followup, updated_at: new Date().toISOString() }] : []),
        { id: 'star_qa_home', area: 'home', branch_id: null, title: 'Casa', statement: 'Informazione di prova', status: 'known', provenance: 'Dati simulati' },
      ], count: removed ? 1 : 2, known_count: removed ? 1 : 2, temporary_count: removed ? 0 : 1, percent: 21, branches: [], revision: removed ? 'qa-v99-removed' : 'qa-v99',
    };
''' + s[b:]
s += '''
// V99: production mobile map -> the SAME Situation card used on desktop.
// API fixtures test rendering/selection/refresh only, not AI or background execution.
test('mobile selected Situation exposes real follow-up fields, scrolls and removes only on success', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 740 });
  const controls = { followup: { status: 'scheduled', next_check_at: '2026-10-08T14:30:00+02:00', last_checked_at: '2026-10-08T13:00:00+02:00', notify_when: 'Una variazione utile rilevata — condizione simulata' }, removeFails: true, dismissed: [] as string[] };
  const posts = await fixture(page, controls);
  await page.getByTestId('ora-mobile-open-map').click();
  const modal = page.getByTestId('ora-mobile-expanded-map');
  const card = modal.getByTestId('ora-cockpit-temporary');
  const scroll = modal.getByTestId('ora-map-detail-scroll');
  await expect(card).toBeVisible();
  await expect(card).toContainText('PANNI STESI');
  await expect(card).toContainText('Controllo programmato');
  await expect(card).toContainText('Prossimo controllo');
  await expect(card).toContainText('Ultimo controllo eseguito');
  await expect(card).toContainText('Quando ti aggiorno in ORA');
  await expect(modal.getByText('Un punto della tua vita', { exact: true })).toHaveCount(0);
  mkdirSync('mobile-qa', { recursive: true });
  await page.screenshot({ path: `mobile-qa/${info.project.name}-situation-v99.png` });
  for (const size of [{ width: 320, height: 568 }, { width: 390, height: 740 }, { width: 740, height: 390 }]) {
    await page.setViewportSize(size);
    await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
    await expect(card.getByTestId('ora-remove-temporary')).toBeInViewport();
    await expect(modal.getByRole('button', { name: 'Chiudi dettagli della mappa' })).toBeInViewport();
    await expect(modal.getByTestId('ora-mobile-close-map')).toBeInViewport();
    const box = await modal.getByTestId('ora-map-detail').boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(size.width + 1);
    expect(box!.y + box!.height).toBeLessThanOrEqual(size.height + 1);
  }
  await page.setViewportSize({ width: 390, height: 740 });
  await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await card.getByTestId('ora-remove-temporary').click();
  await expect(card).toContainText('Non sono riuscita a rimuovere');
  await expect(card).toBeVisible();
  controls.removeFails = false;
  await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await card.getByTestId('ora-remove-temporary').click();
  await expect(card).toHaveCount(0);
  await expect(modal.getByTestId('knowledge-map-progress')).toContainText('1 stelle');
  expect(controls.dismissed).toEqual(Array(2).fill('/api/life-profile/knowledge-map/situations/sit_qa_1/dismiss'));
  expect(posts).toEqual([]);
});

test('mobile follow-up starts unconfirmed and refreshes without a chat message', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 740 });
  const controls = { followup: { status: 'not_scheduled' } as any };
  const posts = await fixture(page, controls);
  await page.getByTestId('ora-mobile-open-map').click();
  const modal = page.getByTestId('ora-mobile-expanded-map');
  const card = modal.getByTestId('ora-cockpit-temporary');
  await expect(card).toContainText('Nessun controllo programmato');
  await expect(card.getByText('Prossimo controllo', { exact: true })).toHaveCount(0);
  controls.followup = { status: 'scheduled', next_check_at: '2026-10-08T14:30:00+02:00', notify_when: 'Condizione di prova' };
  await expect(card).toContainText('Controllo programmato', { timeout: 25000 });
  await expect(card).toContainText('Prossimo controllo');
  await modal.getByRole('button', { name: 'Chiudi dettagli della mappa' }).click();
  await expect(card).toHaveCount(0);
  await modal.getByTestId('ora-mobile-close-map').click();
  expect(posts).toEqual([]);
});
'''
p.write_text(s)
print('Patched shared Situation card, mobile selection, read-only refresh and browser regressions.')
