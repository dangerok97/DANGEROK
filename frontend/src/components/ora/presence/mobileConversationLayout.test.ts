import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mobileConversationLayout, remainingVisualHeight } from './mobileConversationLayout.ts';

test('phone preview is bounded; it never owns most of the viewport', () => {
  for (const height of [480, 568, 640, 707, 740, 844, 1000]) {
    const layout = mobileConversationLayout(height, false);
    assert.ok(layout.previewHeight >= 76 && layout.previewHeight <= 128);
    assert.ok(layout.previewHeight < height * 0.28);
  }
});
test('keyboard and short landscape windows reserve all available space for chat', () => {
  for (const height of [240, 320, 360, 420, 740]) assert.equal(mobileConversationLayout(height, true).previewHeight, 0);
  for (const height of [240, 320, 360, 420]) assert.equal(mobileConversationLayout(height, false).showPreview, false);
});
test('visual viewport budget respects contextual chrome and insets', () => {
  assert.equal(remainingVisualHeight(360, 0, 0), 360);
  assert.equal(remainingVisualHeight(360, 100, 140, 12), 308);
  assert.equal(remainingVisualHeight(360, 100, 50), 360);
  assert.equal(remainingVisualHeight(30, 0, 60), 0);
  assert.equal(remainingVisualHeight(NaN, 0, 0), null);
});
test('mobile renderer keeps actual conversation and footer, no 164px overlay', () => {
  const source = readFileSync(new URL('./OraPresence.web.tsx', import.meta.url), 'utf8');
  assert.ok(source.includes('ora-mobile-conversation-panel'));
  assert.ok(source.includes('{conversation ||'));
  assert.ok(source.includes('testID="ora-presence-footer">{footer}'));
  assert.ok(source.includes('ora-mobile-open-map') && source.includes('ora-mobile-close-map'));
  assert.ok(!source.includes('transcriptHeight') && !source.includes('position: \'absolute\''));
  assert.ok(source.includes('openingSession.claim'));
  assert.ok(!/aiCore(Start|Message)|fetch\(/.test(source), 'no second session/send path');
});
