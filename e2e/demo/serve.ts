import { createReadStream, readFileSync, statSync } from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import path from 'node:path';

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.wasm': 'application/wasm',
  '.bin': 'application/octet-stream',
  '.pdf': 'application/pdf',
  '.txt': 'text/plain; charset=utf-8',
};

interface Rule {
  from: RegExp;
  to: string;
  status: number;
}

/** The site's _redirects, as Cloudflare Pages reads them. */
function rules(root: string): Rule[] {
  let text = '';
  try {
    text = readFileSync(path.join(root, '_redirects'), 'utf8');
  } catch {
    return [];
  }
  return text
    .split('\n')
    .map((line) => line.trim().split(/\s+/))
    .filter((rule) => rule.length >= 2 && !rule[0].startsWith('#'))
    .map(([from, to, status = '302']) => ({
      from: new RegExp(`^${from.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '(.*)')}$`),
      to,
      status: Number(status),
    }));
}

/** Serves a built demo as Cloudflare Pages would: the file, the file with .html, the folder's
    index, else the site's _redirects; what none of them finds is a 404. `reached` lists what was
    asked of /api, which a demo answers by itself. */
export async function serve(
  root: string,
): Promise<{ origin: string; reached: string[]; close: () => void }> {
  const reached: string[] = [];
  const redirects = rules(root);
  const file = (at: string): string | null => {
    for (const each of [at, `${at}.html`, path.join(at, 'index.html')]) {
      try {
        if (statSync(each).isFile()) return each;
      } catch {
        // the next candidate
      }
    }
    return null;
  };
  const local = (pathname: string): string | null => {
    const at = path.join(root, path.normalize(decodeURIComponent(pathname)));
    return at.startsWith(root) ? file(at) : null;
  };
  const server = http.createServer((request, response) => {
    const { pathname, search } = new URL(request.url!, 'http://demo');
    // The demo answers its API in the page and its worker; what comes here would be a server's.
    if (pathname.startsWith('/api/')) {
      reached.push(`${request.method} ${pathname}${search}`);
      response.writeHead(502);
      response.end();
      return;
    }
    let found = local(pathname);
    if (!found) {
      const rule = redirects.find((each) => each.from.test(pathname));
      const to = rule && rule.to.replace(':splat', pathname.match(rule.from)?.[1] ?? '');
      if (rule && to && rule.status !== 200) {
        response.writeHead(rule.status, { Location: to });
        response.end();
        return;
      }
      found = to ? local(to) : null;
    }
    if (!found) {
      response.writeHead(404);
      response.end();
      return;
    }
    response.writeHead(200, {
      'Content-Type': TYPES[path.extname(found)] ?? 'application/octet-stream',
    });
    createReadStream(found).pipe(response);
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    origin: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    reached,
    close: () => server.close(),
  };
}
