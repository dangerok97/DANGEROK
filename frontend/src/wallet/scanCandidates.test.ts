import { test } from 'node:test';
import assert from 'node:assert/strict';
import { collapseScanCandidates, safePreview } from './scanCandidates.ts';

const ean = { format: 'EAN_13', code: '0042100005264' };
const upc = { format: 'UPC_A', code: '042100005264' };

test('one physical EAN/UPC barcode auto-resolves independent of input order', () => {
  assert.deepEqual(collapseScanCandidates([ean, upc]), [ean]);
  assert.deepEqual(collapseScanCandidates([upc, ean]), [ean]);
});
test('leading digits and arbitrary format distinctions are preserved', () => {
  const code128 = { format: 'CODE_128', code: ean.code };
  const qr = { format: 'QR_CODE', code: ean.code };
  assert.equal(collapseScanCandidates([ean, upc, code128, qr]).length, 3);
  assert.deepEqual(collapseScanCandidates([upc]), [upc]);
});
test('different physical codes still require a real choice', () => {
  const another = { format: 'EAN_13', code: '5901234123457' };
  assert.deepEqual(collapseScanCandidates([ean, upc, another]), [ean, another]);
});
test('invalid checksums are never repaired or merged', () => {
  const a = { format: 'EAN_13', code: '0042100005265' };
  const b = { format: 'UPC_A', code: '042100005265' };
  assert.equal(collapseScanCandidates([a, b]).length, 2);
});
test('duplicate entries collapse and retain a generated preview', () => {
  const preview = { ...ean, image: 'data:image/png;base64,YQ==' };
  assert.deepEqual(collapseScanCandidates([ean, preview, upc]), [preview]);
  assert.deepEqual(collapseScanCandidates([]), []);
});
test('preview cannot navigate to a remote or executable source', () => {
  assert.equal(safePreview('https://example.invalid/image'), null);
  assert.equal(safePreview('data:image/svg+xml;base64,YQ=='), null);
  assert.equal(safePreview('data:image/png;base64,YQ=='), 'data:image/png;base64,YQ==');
});
