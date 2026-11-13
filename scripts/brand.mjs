import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const output = resolve(process.argv[2] ?? '/brand');
const master = await readFile(resolve(output, 'source/identity.svg'), 'utf8');
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  const assets = await page.evaluate((master) => {
    const document = new DOMParser().parseFromString(master, 'image/svg+xml');
    if (document.querySelector('parsererror, image, text, foreignObject, script')) {
      throw new Error('Brand master must be a self-contained vector with outlined lettering');
    }
    const svg = document.documentElement;
    const mark = document.querySelector('#mark');
    const wordmark = document.querySelector('#wordmark');
    const defs = document.querySelector('defs');
    if (!mark || !wordmark || !defs) throw new Error('Incomplete brand master');
    const serialize = node => new XMLSerializer().serializeToString(node);
    const logo = serialize(svg);
    wordmark.setAttribute('fill', '#F7FAF6');
    const inverse = serialize(svg);
    const wrap = (viewBox, width, height, content) =>
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${viewBox}">${serialize(defs)}${content}</svg>`;
    const symbol = wrap('75 85 630 460', 630, 460, serialize(mark));
    // A small icon frames the mark's body: the outer sheets' thin tips, under a pixel at these sizes, run off the edges.
    const body = '120 69 500 500';
    const favicon = wrap(body, 512, 512, serialize(mark));
    // A launcher masks a tile to its own shape and keeps at least the centred circle of 80 % of the side: the body,
    // centred at (370 319), fills that circle and only the tail's tip may fall outside it.
    const tile = wrap('0 0 512 512', 512, 512,
      `<rect width="512" height="512" fill="#F7FAF6"/><g transform="translate(-10.4 26.32) scale(.72)">${serialize(mark)}</g>`);
    // A badge is the mark's silhouette alone, without the paper's shadow: Android's status bar paints it in one colour.
    const silhouette = serialize(mark).replace(/ filter="[^"]*"/, '').replace(/(fill|stroke)="(?!none)[^"]*"/g, '$1="#FFFFFF"');
    const badge = wrap(body, 512, 512, silhouette);
    const size = [Number(svg.getAttribute('width')), Number(svg.getAttribute('height'))];
    return { logo, inverse, size, mark: symbol, favicon, tile, badge };
  }, master);

  await mkdir(output, { recursive: true });
  for (const [name, content] of Object.entries({ 'logo.svg': assets.logo, 'logo-inverse.svg': assets.inverse, 'mark.svg': assets.mark, 'favicon.svg': assets.favicon })) {
    await writeFile(resolve(output, name), `${content}\n`);
  }
  async function png(svg, width, height) {
    await page.setViewportSize({ width, height });
    await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:100vw;height:100vh}</style>${svg}`);
    return page.screenshot({ omitBackground: true });
  }
  await writeFile(resolve(output, 'logo.png'), await png(assets.logo, ...assets.size));
  await writeFile(resolve(output, 'logo-inverse.png'), await png(assets.inverse, ...assets.size));
  await writeFile(resolve(output, 'mark.png'), await png(assets.mark, 630, 460));
  // A desktop window draws the app icon on its own title bar, where a tile of the bar's colour would only shrink the mark.
  for (const size of [192, 512]) await writeFile(resolve(output, `icon-${size}.png`), await png(assets.favicon, size, size));
  await writeFile(resolve(output, 'icon-180.png'), await png(assets.tile, 180, 180));
  await writeFile(resolve(output, 'icon-maskable-512.png'), await png(assets.tile, 512, 512));
  await writeFile(resolve(output, 'badge-96.png'), await png(assets.badge, 96, 96));
  const sizes = [16, 32, 48, 64];
  const images = [];
  for (const size of sizes) images.push(await png(assets.favicon, size, size));
  const header = Buffer.alloc(6 + sizes.length * 16);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(sizes.length, 4);
  let offset = header.length;
  images.forEach((buffer, index) => {
    const entry = 6 + index * 16;
    header[entry] = header[entry + 1] = sizes[index];
    header.writeUInt16LE(1, entry + 4);
    header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(buffer.length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += buffer.length;
  });
  await writeFile(resolve(output, 'favicon.ico'), Buffer.concat([header, ...images]));
} finally {
  await browser.close();
}
console.log(`Brand assets written to ${output}`);
