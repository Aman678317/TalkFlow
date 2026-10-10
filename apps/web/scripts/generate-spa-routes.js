import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, '../dist');
const indexPath = path.join(distDir, 'index.html');

if (!fs.existsSync(indexPath)) {
  console.error('index.html not found in dist');
  process.exit(1);
}

const html = fs.readFileSync(indexPath, 'utf-8');

// 404 fallback
fs.writeFileSync(path.join(distDir, '404.html'), html);

const routes = [
  'agents',
  'agent-studio',
  'translate',
  'write',
  'voice',
  'meetings',
  'meeting',
  'join',
  'documents',
  'dashboard',
  'chat',
  'history',
  'glossaries',
  'translation-memory',
  'style-profiles',
  'usage',
  'billing',
  'settings',
  'team',
  'admin',
  'login',
  'signup',
  'docs',
];

for (const route of routes) {
  const dir = path.join(distDir, route);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(path.join(dir, 'index.html'), html);
}

console.log(`Generated SPA route stubs for ${routes.length} routes + 404.html`);
