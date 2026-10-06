import { createServer } from 'node:http';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve, extname, sep } from 'node:path';
const root = resolve('dist-mobile-qa');
const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.ico': 'image/x-icon' };
createServer((req, res) => {
  try {
    const path = decodeURIComponent(new URL(req.url || '/', 'http://localhost').pathname);
    if (path.startsWith('/api/')) {
      const json = path === '/api/places'
        ? { places: [], candidates: [], routines: [], pending_candidates: false, permission: { preference: 'off', state: 'off' } }
        : path === '/api/financial/overview'
          ? { collegamento: { stato: 'non_collegato', in_parole: 'Nessuna banca collegata.' }, conti: [], cosa_ho_capito: [], fonti_non_piu_collegate: [], collegato_alla_tua_vita: [], da_capire: [], movimenti_recenti: [], vale_la_pena_mostrarlo: false }
          : {};
      res.writeHead(200, {
        'content-type': 'application/json',
        'cache-control': 'no-store',
        'access-control-allow-origin': String(req.headers.origin || 'http://127.0.0.1:8093'),
        'access-control-allow-credentials': 'true',
        'access-control-allow-headers': 'authorization, content-type',
        'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
      });
      res.end(JSON.stringify(json));
      return;
    }
    let file = resolve(root, `.${path}`);
    if (file !== root && !file.startsWith(root + sep)) { res.writeHead(403); res.end(); return; }
    if (!existsSync(file) || !statSync(file).isFile()) file = resolve(root, 'index.html');
    res.writeHead(200, { 'content-type': mime[extname(file)] || 'application/octet-stream', 'cache-control': 'no-store' });
    res.end(readFileSync(file));
  } catch { res.writeHead(500); res.end('Local QA server error'); }
}).listen(8093, '127.0.0.1');
