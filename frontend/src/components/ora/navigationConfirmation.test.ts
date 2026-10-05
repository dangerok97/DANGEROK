import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const screen = readFileSync(
  resolve(FRONTEND, 'src/components/ora/OraConversationScreen.tsx'),
  'utf8',
);

assert.ok(
  screen.includes("type === 'open_navigation'"),
  'la chat deve eseguire l handoff di navigazione confermato',
);
assert.ok(
  screen.includes("'www.google.com'") &&
    screen.includes("'maps.apple.com'") &&
    screen.includes("'waze.com'"),
  'l handoff deve accettare solo provider di navigazione esplicitamente ammessi',
);
assert.ok(
  screen.includes("location.assign(safeUrl)") &&
    screen.includes("Linking.openURL(safeUrl)"),
  'la navigazione deve aprirsi davvero sia sul web sia sulle app native',
);
assert.ok(
  screen.includes("isNavigation ? 'Apro la navigazione…'"),
  'l utente deve vedere che ORA sta eseguendo la navigazione, non una generica attesa',
);

console.log('Navigation confirmation client guards: tutte le asserzioni passate');
