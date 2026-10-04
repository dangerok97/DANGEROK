import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const plugin = fs.readFileSync(path.join(here, '../../plugins/withOraSiri.js'), 'utf8');
const config = fs.readFileSync(path.join(here, '../../app.config.ts'), 'utf8');
const conversation = fs.readFileSync(path.join(here, '../../app/conversation/index.tsx'), 'utf8');

test('Siri App Intent hands free-form requests into the existing conversation route', () => {
  assert.match(plugin, /struct AskOraIntent: AppIntent/);
  assert.match(plugin, /@Parameter\(title: "Richiesta"/);
  assert.match(plugin, /components\.scheme = "ora"/);
  assert.match(plugin, /components\.host = "conversation"/);
  assert.match(plugin, /URLQueryItem\(name: "text", value: trimmed\)/);
  assert.match(plugin, /URLQueryItem\(name: "origin", value: "siri"\)/);
  assert.match(conversation, /useLocalSearchParams<\{ text\?: string/);
  assert.match(conversation, /ConversationEngine\.start\(text, router/);
});

test('Siri shortcut uses App Shortcuts and immediate foreground mode', () => {
  assert.match(plugin, /struct OraShortcuts: AppShortcutsProvider/);
  assert.match(plugin, /static var supportedModes: IntentModes = \[\.foreground\(\.immediate\)\]/);
  assert.match(plugin, /Dì a \\\\?\(\.applicationName\)/);
  assert.match(config, /\.\/plugins\/withOraSiri/);
});
