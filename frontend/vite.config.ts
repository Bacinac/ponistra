import { createHash } from 'node:crypto';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';
import { IMPORTED } from './src/importable.ts';

const require = createRequire(import.meta.url);
const PDFJS = dirname(require.resolve('pdfjs-dist/package.json'));
const LANGUAGE_DATA = join(dirname(require.resolve('@codemirror/language-data')), '..');
const PDFJS_DATA = ['cmaps', 'standard_fonts', 'wasm', 'iccs', 'web/images'];
// MediaPipe's package exports its files but not its package.json.
const VISION = dirname(require.resolve('@mediapipe/tasks-vision'));
const VISION_DATA = ['wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm'];
const VISION_BASE = 'assets/tasks-vision-';
const VISION_MODULE = 'virtual:vision';
const PACKAGED_TYPES: Record<string, string> = {
  '.wasm': 'application/wasm',
  '.js': 'text/javascript',
  '.svg': 'image/svg+xml',
};

/** The owner's code workspace (D34) opens only through the backend's door, which Caddy asks in an
 * installation: a reader it turns away goes back to the app, a WebSocket is refused. */
async function workspaceDoor(req: IncomingMessage, res: ServerResponse | undefined) {
  const door = await fetch('http://backend:8030/api/workspace/door', {
    headers: { cookie: req.headers.cookie ?? '' },
  }).catch(() => null);
  if (door?.status === 204 && req.url !== '/code') return undefined;
  res?.writeHead(302, { Location: door?.status === 204 ? '/code/' : '/' }).end();
  return false;
}

/** Files a package fetches by URL as it runs, served from the package as they are, under its
 * version: pdf.js its character maps, standard fonts, decoders, colour profiles and annotation
 * icons (`pdf/PdfView.tsx`), MediaPipe the wasm of its vision tasks (`camera.ts`). */
function packaged(name: string, root: string, files: string[]): Plugin[] {
  const { version } = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  const base = `assets/${name}-${version}/`;
  return [
    {
      name: `${name}-data:serve`,
      apply: 'serve',
      configureServer(server) {
        server.middlewares.use(`/${base}`, (request, response, next) => {
          const file = (request.url ?? '').split('?')[0].slice(1);
          if (!files.includes(file)) return next();
          response.setHeader(
            'Content-Type',
            PACKAGED_TYPES[extname(file)] ?? 'application/octet-stream',
          );
          response.end(readFileSync(join(root, file)));
        });
      },
    },
    {
      name: `${name}-data:build`,
      apply: 'build',
      buildStart() {
        for (const file of files) {
          this.emitFile({
            type: 'asset',
            fileName: `${base}${file}`,
            source: readFileSync(join(root, file)),
          });
        }
      },
    },
  ];
}

function pdfjsData(): Plugin[] {
  return packaged(
    'pdfjs',
    PDFJS,
    PDFJS_DATA.flatMap((dir) => readdirSync(join(PDFJS, dir)).map((file) => `${dir}/${file}`)),
  );
}

/** MediaPipe's wasm, whose folder `virtual:vision` names to the camera's processing. */
function visionData(): Plugin[] {
  const { version } = JSON.parse(readFileSync(join(VISION, 'package.json'), 'utf8'));
  return [
    ...packaged('tasks-vision', VISION, VISION_DATA),
    {
      name: 'tasks-vision-data:module',
      resolveId: (id) => (id === VISION_MODULE ? `\0${VISION_MODULE}` : undefined),
      load: (id) =>
        id === `\0${VISION_MODULE}`
          ? `export default ${JSON.stringify(`/${VISION_BASE}${version}/wasm`)};`
          : undefined,
    },
  ];
}

const BRAND = 'src/assets/brand';
/** The icons the manifest and the service worker name at the root, from the brand folder. */
const ICONS: [string, string, string][] = [
  ['icon-192.png', '192x192', 'any'],
  ['icon-512.png', '512x512', 'any'],
  ['icon-maskable-512.png', '512x512', 'maskable'],
  ['badge-96.png', '96x96', 'monochrome'],
];
/** An installed app takes a changed icon only when the manifest gives it a new address, so each
 * icon's address carries a digest of its content. */
function fingerprinted(file: string) {
  const digest = createHash('sha256')
    .update(readFileSync(join(BRAND, file)))
    .digest('hex');
  return `/${file}?${digest.slice(0, 12)}`;
}
/** Read when asked, not imported, so that a changed string does not restart the dev server. */
async function strings(language: 'hr' | 'en'): Promise<Record<string, string>> {
  const file = resolve('src/i18n', `${language}.ts`);
  const read = await import(`${pathToFileURL(file).href}?${statSync(file).mtimeMs}`);
  return read[language];
}

async function manifest(language: 'hr' | 'en'): Promise<string> {
  const said = await strings(language);
  return JSON.stringify({
    id: '/',
    name: 'Ponistra',
    short_name: 'Ponistra',
    description: said['app.description'],
    start_url: '/',
    scope: '/',
    display: 'standalone',
    lang: language,
    background_color: '#f7faf6',
    theme_color: '#f7faf6',
    launch_handler: { client_mode: ['focus-existing', 'auto'] },
    file_handlers: [
      {
        action: '/documents',
        accept: Object.fromEntries(
          Object.entries({ ...IMPORTED, 'application/pdf': '.pdf' }).map(([type, extension]) => [
            type,
            [extension],
          ]),
        ),
      },
    ],
    protocol_handlers: [{ protocol: 'mailto', url: '/mail?mailto=%s' }],
    shortcuts: [
      { name: said['notes.new'], short_name: said['app.noteShort'], url: '/notes?new' },
      { name: said['speech.say'], short_name: said['app.voiceShort'], url: '/?voice' },
    ],
    share_target: {
      action: '/share',
      method: 'POST',
      enctype: 'multipart/form-data',
      params: {
        title: 'title',
        text: 'text',
        url: 'url',
        files: [{ name: 'files', accept: ['*/*'] }],
      },
    },
    icons: ICONS.filter(([, , purpose]) => purpose !== 'monochrome').map(
      ([file, sizes, purpose]) => ({
        src: fingerprinted(file),
        sizes,
        type: 'image/png',
        purpose,
      }),
    ),
  });
}

/** What the browser installs the app by: the service worker at the root, where its scope is the
 * whole app, the icons, and the manifest, served from the sources in development and emitted at
 * the root in a build, a manifest in each language. The demo's worker stands in for the app's. */
const rooted = (worker: string): [string, string, () => Buffer | string | Promise<string>][] => [
  ['sw.js', 'text/javascript', () => readFileSync(worker)],
  ...ICONS.map(([file]): [string, string, () => Buffer] => [
    file,
    'image/png',
    () => readFileSync(join(BRAND, file)),
  ]),
  ...(['hr', 'en'] as const).map((language): [string, string, () => Promise<string>] => [
    language === 'hr' ? 'manifest.webmanifest' : `manifest.${language}.webmanifest`,
    'application/manifest+json',
    () => manifest(language),
  ]),
];

/** The phone's own app as `android/build.sh` shelves it, mounted here: the APK, what the app
 * reads of it before updating, and the statement that lets Chrome show this installation inside
 * the app (D26). An installation without the shelf answers 404 for them, never the app's page. */
const SHELF = '/android';
const HELP_SHOTS = '/shots';
const ASSET_LINKS = '.well-known/assetlinks.json';
const SHELF_MODULE = 'virtual:android';

function aboutShelf() {
  const about = join(SHELF, 'ponistra.json');
  return existsSync(about) ? JSON.parse(readFileSync(about, 'utf8')) : null;
}

function shelved(): [string, string, () => Buffer | string][] {
  const about = aboutShelf();
  if (!about) return [];
  return [
    ['android/ponistra.json', 'application/json', () => readFileSync(join(SHELF, 'ponistra.json'))],
    [
      'android/ponistra.apk',
      'application/vnd.android.package-archive',
      () => readFileSync(join(SHELF, 'ponistra.apk')),
    ],
    [
      ASSET_LINKS,
      'application/json',
      () =>
        JSON.stringify([
          {
            relation: ['delegate_permission/common.handle_all_urls'],
            target: {
              namespace: 'android_app',
              package_name: about.package,
              sha256_cert_fingerprints: [about.signerSha256.toUpperCase().match(/../g).join(':')],
            },
          },
        ]),
    ],
  ];
}

/** The help's pictures, made each night (scripts/check.sh), in no part of the module graph: an
    article names them only as it renders. */
function helpShots(): Plugin[] {
  const held = () =>
    existsSync(HELP_SHOTS) ? readdirSync(HELP_SHOTS).filter((file) => file.endsWith('.webp')) : [];
  return [
    {
      name: 'help-shots:serve',
      apply: 'serve',
      configureServer(server) {
        server.middlewares.use('/help-shots/', (request, response, next) => {
          const file = basename((request.url ?? '').split('?')[0]);
          if (!held().includes(file)) return next();
          response.setHeader('Content-Type', 'image/webp');
          response.end(readFileSync(join(HELP_SHOTS, file)));
        });
      },
    },
    {
      name: 'help-shots:build',
      apply: 'build',
      buildStart() {
        for (const file of held()) {
          this.emitFile({
            type: 'asset',
            fileName: `help-shots/${file}`,
            source: readFileSync(join(HELP_SHOTS, file)),
          });
        }
      },
    },
  ];
}

function installable(worker: string): Plugin[] {
  const ROOT = rooted(worker);
  return [
    {
      name: 'installable:serve',
      apply: 'serve',
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const path = (request.url ?? '').split('?')[0];
          const shelf = path.startsWith('/android/') || path === `/${ASSET_LINKS}`;
          const found = [...ROOT, ...(shelf ? shelved() : [])].find(
            ([file]) => path === `/${file}`,
          );
          if (!found && !shelf) return next();
          if (!found) {
            response.statusCode = 404;
            return response.end();
          }
          response.setHeader('Content-Type', found[1]);
          // The tunnel keeps an .apk by its extension unless told otherwise.
          if (shelf) response.setHeader('Cache-Control', 'no-cache');
          void Promise.resolve(found[2]()).then((body) => response.end(body), next);
        });
      },
    },
    {
      // The page learns what the shelf holds from its build, not by asking for a file that may be
      // missing, each such 404 an error in the browser's console.
      name: 'installable:shelf',
      resolveId: (id) => (id === SHELF_MODULE ? `\0${SHELF_MODULE}` : undefined),
      load(id) {
        if (id !== `\0${SHELF_MODULE}`) return;
        const about = aboutShelf();
        const shown = about && { versionName: about.versionName, bytes: about.bytes };
        return `export default ${JSON.stringify(shown)};`;
      },
      configureServer(server) {
        server.watcher.add(SHELF);
        const changed = (file: string) => {
          const module = server.moduleGraph.getModuleById(`\0${SHELF_MODULE}`);
          if (dirname(file) === SHELF && module) void server.reloadModule(module);
        };
        server.watcher.on('add', changed).on('change', changed).on('unlink', changed);
      },
    },
    {
      name: 'installable:build',
      apply: 'build',
      async buildStart() {
        for (const [file, , source] of [...ROOT, ...shelved()]) {
          this.emitFile({ type: 'asset', fileName: file, source: await source() });
        }
      },
      // A device marked to work without the network (D45) keeps the whole app, every page's
      // chunk included, by this list.
      generateBundle(_, bundle) {
        const assets = Object.keys(bundle)
          // A meeting needs the network, so MediaPipe's 15 MB stay out.
          .filter(
            (file) =>
              file.startsWith('assets/') && !file.endsWith('.map') && !file.startsWith(VISION_BASE),
          )
          .map((file) => `/${file}`)
          .sort();
        this.emitFile({ type: 'asset', fileName: 'assets.json', source: JSON.stringify(assets) });
      },
    },
  ];
}

/** Lightning CSS stands in for light-dark() below its targets with variables that only a literal
 * color-scheme sets, which theme.css's `var(--scheme)` is not: every colour of the interface
 * would come out void, in the build alone. */
function nativeLightDark(): Plugin {
  return {
    name: 'native-light-dark',
    apply: 'build',
    generateBundle(_, bundle) {
      for (const file of Object.values(bundle)) {
        if (file.type === 'asset' && file.fileName.endsWith('.css')) {
          if (String(file.source).includes('--lightningcss-')) {
            this.error(`${file.fileName} carries Lightning CSS's light-dark() stand-in`);
          }
        }
      }
    },
  };
}

/** The public demo (`vite build --mode demo`): the app over what a walk through the backend
 * recorded (`demo/recorded/`, or `PONISTRA_DEMO_RECORDING`), with `demo/start.ts` answering the
 * server's part in the browser before the app starts. Nothing of it reaches any other mode. */
const DEMO_RECORDING = 'demo-recording';

interface Credit {
  work: string;
  author: string;
  licence: string;
  source: string;
  change?: string;
}

function recordedFiles(root: string, under = ''): string[] {
  return readdirSync(join(root, under), { withFileTypes: true }).flatMap((entry) => {
    const path = under ? `${under}/${entry.name}` : entry.name;
    return entry.isDirectory() ? recordedFiles(root, path) : [path];
  });
}

function creditsPage(recording: string): string {
  const escaped = (text: string) =>
    text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
  const { credits = [] } = JSON.parse(readFileSync(join(recording, 'meta.json'), 'utf8')) as {
    credits?: Credit[];
  };
  const rows = credits
    .map((credit) => {
      const source = /^https?:\/\//.test(credit.source)
        ? `<a href="${escaped(credit.source)}">${escaped(credit.source)}</a>`
        : escaped(credit.source);
      return `<tr><td>${escaped(credit.work)}</td><td>${escaped(credit.author)}</td><td>${escaped(credit.licence)}</td><td>${source}</td><td>${escaped(credit.change ?? '')}</td></tr>`;
    })
    .join('\n');
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Credits – Ponistra demo</title>
<style>
:root { color-scheme: light dark; --surface: #f7faf6; --ink: #1d2b2b; --muted: #5b6b68; --line: #d5ddd8; --accent: #1f5f66; }
@media (prefers-color-scheme: dark) { :root { --surface: #121a1a; --ink: #e4ece8; --muted: #9aaba6; --line: #2b3837; --accent: #8cc7c0; } }
body { margin: 0; padding: 2rem 1rem; background: var(--surface); color: var(--ink); font: 15px/1.5 system-ui, sans-serif; }
main { max-width: 64rem; margin: 0 auto; }
p { color: var(--muted); }
a { color: var(--accent); }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; vertical-align: top; padding: .4rem .6rem; border-bottom: 1px solid var(--line); }
th { font-weight: 600; }
</style>
</head>
<body>
<main>
<h1>Credits</h1>
<p>The company, its people, mail, documents and everything else in the Ponistra demo are invented. These are the works it shows that others made.</p>
<div class="scroll"><table>
<thead><tr><th>Work</th><th>Author</th><th>Licence</th><th>Source</th><th>Change</th></tr></thead>
<tbody>
${rows}
</tbody>
</table></div>
<p><a href="/">Back to the demo</a></p>
</main>
</body>
</html>
`;
}

function demo(): Plugin[] {
  const recording = resolve(process.env.PONISTRA_DEMO_RECORDING ?? 'demo/recorded');
  const missing = ['meta.json', 'responses.json'].filter(
    (file) => !existsSync(join(recording, file)),
  );
  if (missing.length) {
    throw new Error(`The demo's recording ${recording} has no ${missing.join(' or ')}`);
  }
  return [
    {
      name: 'demo:entry',
      transformIndexHtml: {
        order: 'pre',
        handler: (html) => {
          if (!html.includes('/src/main.tsx')) {
            throw new Error('index.html no longer loads /src/main.tsx');
          }
          return html.replace('/src/main.tsx', '/demo/start.ts');
        },
      },
    },
    {
      name: 'demo:serve',
      apply: 'serve',
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const path = decodeURIComponent((request.url ?? '').split('?')[0]);
          if (path === `/${DEMO_RECORDING}/files.json`) {
            response.setHeader('Content-Type', 'application/json');
            return response.end(JSON.stringify(recordedFiles(recording)));
          }
          if (path === '/demo-credits.html') {
            response.setHeader('Content-Type', 'text/html; charset=utf-8');
            return response.end(creditsPage(recording));
          }
          if (!path.startsWith(`/${DEMO_RECORDING}/`)) return next();
          const file = resolve(recording, path.slice(DEMO_RECORDING.length + 2));
          if (!file.startsWith(`${recording}/`) || !existsSync(file)) {
            response.statusCode = 404;
            return response.end();
          }
          response.end(readFileSync(file));
        });
      },
    },
    {
      name: 'demo:build',
      apply: 'build',
      buildStart() {
        const files = recordedFiles(recording);
        // Pages answers a missing file with the app's page, so the demo asks this list instead.
        this.emitFile({
          type: 'asset',
          fileName: `${DEMO_RECORDING}/files.json`,
          source: JSON.stringify(files),
        });
        for (const file of files) {
          this.emitFile({
            type: 'asset',
            fileName: `${DEMO_RECORDING}/${file}`,
            source: readFileSync(join(recording, file)),
          });
        }
        this.emitFile({
          type: 'asset',
          fileName: 'demo-credits.html',
          source: creditsPage(recording),
        });
        // Cloudflare Pages answers every route the app has with its page.
        this.emitFile({ type: 'asset', fileName: '_redirects', source: '/*  /index.html  200\n' });
      },
    },
  ];
}

export default defineConfig(({ command, mode }) => ({
  // Tailwind's own pass targets browsers without light-dark(), so Vite's minifier alone takes the
  // CSS to cssTarget, the browsers that have it.
  plugins: [
    react(),
    tailwindcss({ optimize: false }),
    pdfjsData(),
    visionData(),
    installable(mode === 'demo' ? 'demo/sw.js' : 'src/sw.js'),
    helpShots(),
    nativeLightDark(),
    ...(mode === 'demo' ? demo() : []),
  ],
  build: {
    cssTarget: ['chrome123', 'edge123', 'firefox120', 'safari17.5', 'ios17.5'],
    // The maps stay in the image beside what it serves (frontend/Dockerfile), for
    // scripts/stack.sh to read a crash's stack the server logged.
    sourcemap: 'hidden',
    // The editor, ECharts and pdf.js are each a chunk of their own, which only the page that needs
    // it loads.
    chunkSizeWarningLimit: 700,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'react', test: /\/node_modules\/(?:react|react-dom|react-router|scheduler)\// },
          ],
        },
      },
    },
  },
  optimizeDeps: {
    // CodeMirror's language data imports each language only once a file asks for it, which Vite
    // would find mid-session and answer with 504 while it bundles the language anew.
    include: [
      ...new Set(
        Array.from(
          readFileSync(join(LANGUAGE_DATA, 'dist/index.js'), 'utf8').matchAll(
            /import\(['"]([^'"]+)['"]\)/g,
          ),
          ([, name]) => name,
        ),
      ),
    ],
  },
  test: {
    // lib0, under Yjs, probes localStorage on import, and Node's own warns when it has no file.
    execArgv: ['--no-experimental-webstorage'],
  },
  server: {
    // The printer loads the print page by the service's own name.
    allowedHosts:
      command === 'serve' ? [new URL(process.env.PONISTRA_PUBLIC_URL!).hostname, 'frontend'] : [],
    // The repository's one fonts/, colors/ and schema/ directories, mounted beside the app.
    fs: { allow: ['.', '../fonts', '../colors', '../schema'] },
    proxy: {
      '/api': { target: 'http://backend:8030', ws: true },
      '^/(dav(/|$)|\\.well-known/(carddav|caldav|oauth-))': { target: 'http://backend:8030' },
      '/livekit': {
        target: `http://${process.env.PONISTRA_LIVEKIT}`,
        ws: true,
        rewrite: (path) => path.replace(/^\/livekit/, ''),
      },
      '^/code/ponistra/': {
        target: 'http://workspace:8081',
        bypass: workspaceDoor,
        rewrite: (path) => path.replace(/^\/code/, ''),
      },
      '^/code(/|$)': {
        target: 'http://workspace:8080',
        ws: true,
        bypass: workspaceDoor,
        rewrite: (path) => path.replace(/^\/code/, ''),
      },
    },
  },
}));
