/**
 * Contesti Life Map mapping helpers.
 * Run: node --experimental-strip-types src/components/contexts/quiet/buildContextsMap.test.ts
 */
import assert from 'node:assert/strict';
import {
  buildContextsMap,
  buildLifeAreas,
  buildLiveSituations,
} from './buildContextsMap.ts';

const now = new Date('2026-08-10T12:00:00.000Z');

const profile = {
  user_id: 'u1',
  domains: {
    mlc: {
      domain: 'mlc',
      objects: { 'mlc.identity.name': { key: 'mlc.identity.name', value: 'Ada' } },
    },
    lavoro: {
      domain: 'lavoro',
      objects: {
        'lavoro.active': { key: 'lavoro.active', value: true },
        'lavoro.ruolo': { key: 'lavoro.ruolo', value: 'Guardia di Finanza' },
      },
    },
    studio: {
      domain: 'studio',
      objects: {
        'studio.active': { key: 'studio.active', value: true },
        'studio.universita': { key: 'studio.universita', value: 'Università' },
      },
    },
    salute: {
      domain: 'salute',
      objects: {},
    },
    mystery: {
      domain: 'mystery',
      objects: { foo: { key: 'foo', value: 'bar' } },
    },
  },
};

const areas = buildLifeAreas(profile);
assert.equal(areas.length, 2, 'only domains with known presentable facts');
assert.deepEqual(
  areas.map((a) => a.domain),
  ['lavoro', 'studio'],
);
assert.equal(areas[0].identity, 'Guardia di Finanza');
assert.equal(areas[1].identity, 'Università');

const emptyAreas = buildLifeAreas({ domains: {} });
assert.equal(emptyAreas.length, 0);

const study = [
  {
    id: 'sp1',
    status: 'active',
    exam_name: 'Psicologia',
    subject: 'Psicologia',
    exam_date: '2026-08-15T09:00:00.000Z',
  },
  {
    id: 'sp2',
    status: 'draft',
    exam_name: 'Draft exam',
    exam_date: '2026-09-01T09:00:00.000Z',
  },
  {
    id: 'sp3',
    status: 'active',
    exam_name: 'Past exam',
    exam_date: '2026-08-01T09:00:00.000Z',
  },
];

const travel = [
  {
    id: 'tp1',
    status: 'active',
    title: 'Vacanza a Vibo Marina',
    destination: 'Vibo Marina',
    start_date: '2026-08-09',
    end_date: '2026-08-24',
    phase: 'during',
  },
  {
    id: 'tp2',
    status: 'completed',
    title: 'Old trip',
    destination: 'Roma',
    start_date: '2026-01-01',
    end_date: '2026-01-07',
  },
];

const situations = buildLiveSituations(study, travel, now);
assert.equal(situations.length, 2, 'active study + travel only; past/draft excluded');
assert.ok(situations.some((s) => s.kind === 'travel' && s.href.includes('tp1')));
assert.ok(situations.some((s) => s.kind === 'study' && s.title === 'Psicologia'));
const psych = situations.find((s) => s.title === 'Psicologia')!;
assert.match(psych.temporal || '', /Esame/);

const map = buildContextsMap({ profile, studyPlans: study, travelProjects: travel, now });
assert.equal(map.areas.length, 2);
assert.equal(map.situations.length, 2);

const onlySituations = buildContextsMap({
  profile: { domains: {} },
  studyPlans: study,
  travelProjects: [],
  now,
});
assert.equal(onlySituations.areas.length, 0);
assert.equal(onlySituations.situations.length, 1);

console.log('buildContextsMap.test.ts OK');
