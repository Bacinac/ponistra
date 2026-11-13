/** POST /pdf with {path, cookie, session, timezone} answers with the print page at `path`, as the
 * session's user reads it, saved as PDF in runs of at most RUN pages, one after another, their
 * lengths in bytes in the X-Runs header; POST /pages with the same answers with the count of each
 * tab's pages there, as JSON by the tabs' ids; POST /slides with the path of the print page's
 * slides answers with each tab's slides as they are laid out there, measured, as JSON by the
 * tabs' ids; POST /png?width=&height= with an SVG answers with a
 * PNG of it at twice that size, drawn as a browser draws an image: without scripts or the network.
 * GET /health answers while the browser is up. Each job has a browser context of its own, two
 * readers' jobs at a time and the counts one at a time beside them, so a count never keeps a
 * reader waiting. */
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { chromium } from 'playwright-core';

const PORT = 8050;
const SITE = 'http://frontend:5173';
const TIMEOUT = 120_000;
const LARGEST = 4096;
// The backend's BLOB_MAX_BYTES.
const LARGEST_PICTURE = 100 * 1024 * 1024;
const SIDE = /^[1-9][0-9]{0,3}$/;
const AT_ONCE = 2;
const RUN = 100;
const EVENTS = '/sys/fs/cgroup/memory.events';
const PATH = /^\/print\/[0-9A-Za-z]{22}(\/slides)?$/;
const COOKIE = /^[A-Za-z0-9_-]{1,64}$/;
const SESSION = /^[0-9a-z]{32}$/;

class Unprinted extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const browser = await chromium.launch({ executablePath: '/usr/bin/chromium-headless-shell' });
// Without its browser the printer prints nothing; Docker starts it again.
browser.on('disconnected', () => {
  console.error('Chromium went away');
  process.exit(1);
});

function lane(size) {
  const waiting = [];
  let free = size;
  return {
    take: () => (free > 0 ? (free--, Promise.resolve()) : new Promise((go) => waiting.push(go))),
    give: () => (waiting.length ? waiting.shift()() : free++),
  };
}

const asked = lane(AT_ONCE);
const counting = lane(1);

function known(timezone) {
  try {
    new Intl.DateTimeFormat('en', { timeZone: timezone });
    return true;
  } catch {
    return false;
  }
}

function valid(asked) {
  return (
    PATH.test(asked?.path) &&
    COOKIE.test(asked.cookie) &&
    SESSION.test(asked.session) &&
    typeof asked.timezone === 'string' &&
    known(asked.timezone)
  );
}

async function laidOut({ path, cookie, session, timezone }, reading) {
  const context = await browser.newContext({ timezoneId: timezone });
  try {
    await context.addCookies([{ name: cookie, value: session, url: SITE }]);
    const page = await context.newPage();
    page.on('pageerror', (error) => console.error(`${path}: ${error.message}`));
    await page.goto(`${SITE}${path}`, { timeout: TIMEOUT });
    const body = page.locator('body[data-printed]');
    await body.waitFor({ state: 'attached', timeout: TIMEOUT });
    if ((await body.getAttribute('data-printed')) !== 'ready') {
      throw new Unprinted(422, `${path} could not be laid out`);
    }
    return await reading(page, body);
  } finally {
    await context.close();
  }
}

async function pagesOf(path, body) {
  const pages = JSON.parse((await body.getAttribute('data-pages')) ?? 'null');
  const valid =
    pages !== null &&
    typeof pages === 'object' &&
    Object.values(pages).every((count) => Number.isInteger(count) && count > 0);
  if (!valid) throw new Unprinted(422, `${path} told no count of its pages`);
  return pages;
}

// Chromium holds all that one print lays out until the PDF is saved, and a document of a thousand
// pages printed whole takes several times the printer's memory. The print page takes its tables'
// other pages out of layout once its body's `data-range` names the run, and tells so in
// `data-ranged`.
const printed = (asked) =>
  laidOut(asked, async (page, body) => {
    const pages = Object.values(await pagesOf(asked.path, body)).reduce(
      (sum, count) => sum + count,
    );
    const runs = [];
    const devtools = await page.context().newCDPSession(page);
    for (let first = 1; first <= pages; first += RUN) {
      const range = `${first}-${Math.min(first + RUN - 1, pages)}`;
      await body.evaluate((body, range) => (body.dataset.range = range), range);
      await page
        .locator(`body[data-ranged="${range}"]`)
        .waitFor({ state: 'attached', timeout: TIMEOUT });
      runs.push(
        await page.pdf({ preferCSSPageSize: true, printBackground: true, pageRanges: range }),
      );
      // Chromium sizes its heap by the host's memory, not the printer's, and would leave each
      // run's rows uncollected until it is far past what the printer has.
      await devtools.send('HeapProfiler.collectGarbage');
    }
    return runs;
  });

const counted = (asked) =>
  laidOut(asked, async (page, body) =>
    Buffer.from(JSON.stringify(await pagesOf(asked.path, body))),
  );

const measured = (asked) =>
  laidOut(asked, async (page, body) => {
    const slides = JSON.parse((await body.getAttribute('data-slides')) ?? 'null');
    if (slides === null || typeof slides !== 'object' || Array.isArray(slides)) {
      throw new Unprinted(422, `${asked.path} told no slides`);
    }
    return Buffer.from(JSON.stringify(slides));
  });

async function drawn(svg, width, height) {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    offline: true,
    viewport: { width, height },
    deviceScaleFactor: 2,
  });
  try {
    const page = await context.newPage();
    const source = `data:image/svg+xml;base64,${svg.toString('base64')}`;
    await page.setContent(
      `<style>body{margin:0}img{display:block;width:${width}px;height:${height}px}</style>` +
        `<img src="${source}">`,
      { timeout: TIMEOUT },
    );
    return await page.screenshot({ omitBackground: true, timeout: TIMEOUT });
  } finally {
    await context.close();
  }
}

async function read(request, largest = LARGEST) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > largest) throw new Unprinted(413, 'request too large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function killed() {
  const events = await readFile(EVENTS, 'utf8');
  return Number(/^oom_kill (\d+)$/m.exec(events)[1]);
}

async function job(response, work, type, failed, { take, give } = asked) {
  await take();
  const kills = await killed();
  try {
    const done = await work();
    const data = Array.isArray(done) ? Buffer.concat(done) : done;
    const headers = { 'Content-Type': type, 'Content-Length': data.length };
    if (Array.isArray(done)) headers['X-Runs'] = done.map((run) => run.length).join(' ');
    response.writeHead(200, headers);
    response.end(data);
  } catch (error) {
    const message =
      (await killed()) > kills
        ? `Chromium ran out of the printer's memory: ${error.message}`
        : error.message;
    console.error(`${failed}: ${message}`);
    const status = error.status ?? (error.name === 'TimeoutError' ? 504 : 500);
    answer(response, status, message);
  } finally {
    give();
  }
}

function answer(response, status, message) {
  response.writeHead(status, { 'Content-Type': 'text/plain' });
  response.end(message);
}

createServer(async (request, response) => {
  const url = new URL(request.url, 'http://printer');
  if (request.method === 'GET' && url.pathname === '/health') return answer(response, 200, 'ok');
  if (request.method === 'POST' && url.pathname === '/png') {
    const [width, height] = ['width', 'height'].map((side) => url.searchParams.get(side) ?? '');
    if (!SIDE.test(width) || !SIDE.test(height)) return answer(response, 400, 'invalid request');
    let svg;
    try {
      svg = await read(request, LARGEST_PICTURE);
    } catch (error) {
      return answer(response, error.status ?? 400, error.message);
    }
    const work = () => drawn(svg, Number(width), Number(height));
    return job(response, work, 'image/png', `a picture of ${svg.length} bytes`);
  }
  if (request.method !== 'POST' || !['/pdf', '/pages', '/slides'].includes(url.pathname)) {
    return answer(response, 404, 'not found');
  }
  let page;
  try {
    page = JSON.parse(await read(request));
  } catch (error) {
    return answer(response, error.status ?? 400, error.message);
  }
  if (!valid(page)) return answer(response, 400, 'invalid request');
  if (url.pathname === '/pages') {
    return job(response, () => counted(page), 'application/json', page.path, counting);
  }
  if (url.pathname === '/slides') {
    return job(response, () => measured(page), 'application/json', page.path);
  }
  return job(response, () => printed(page), 'application/pdf', page.path);
}).listen(PORT);
