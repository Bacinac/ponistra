import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const output = resolve(process.argv[2] ?? '/brand');
const android = resolve(process.argv[3] ?? '/android');
const master = await readFile(resolve(output, 'source/identity.svg'), 'utf8');
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  const brand = await page.evaluate(async (master) => {
    const source = new DOMParser().parseFromString(master, 'image/svg+xml');
    if (source.querySelector('parsererror, image, text, foreignObject, script')) {
      throw new Error('Brand master must be a self-contained vector with outlined lettering');
    }
    const svg = source.documentElement;
    const wordmark = source.querySelector('#wordmark');
    const mark = source.querySelector('#mark');
    const cut = source.querySelector('mask#cut');
    const fill = source.querySelector('linearGradient#tile-fill');
    const tile = source.querySelector('symbol#tile');
    if (!wordmark || !mark || !cut || !fill || !tile) throw new Error('Incomplete brand master');
    const serialize = (node) => new XMLSerializer().serializeToString(node);
    const strip = (node) => serialize(node).replace(/ xmlns(:\w+)?="[^"]*"/g, '');
    const ink = wordmark.getAttribute('stroke');
    const inverse = wordmark.getAttribute('data-inverse');
    const pen = ['stroke-width', 'stroke-linecap', 'stroke-linejoin']
      .map((name) => `${name}="${wordmark.getAttribute(name)}"`)
      .join(' ');
    const letter = mark.cloneNode();
    letter.removeAttribute('id');
    const glyph = (colour, extra = '') =>
      `<g fill="none" stroke="${colour}" ${pen}${extra}>${strip(letter)}</g>`;
    const drawing = (viewBox, defs, body, label = 'Ponistra') =>
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" role="img" aria-label="${label}"><title>${label}</title><defs>${defs}</defs>${body}</svg>`;

    const [x, y, width, height] = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    const words = wordmark.cloneNode(true);
    words.removeAttribute('id');
    words.removeAttribute('data-inverse');
    words.querySelector('#mark').removeAttribute('id');
    const logo = (colour) => {
      words.setAttribute('stroke', colour);
      return drawing(svg.getAttribute('viewBox'), strip(cut), strip(words)).replace(
        '<svg ',
        `<svg width="${width}" height="${height}" `,
      );
    };

    // The mark is framed on its measured ink, not on the 96-unit glyph box, so its geometry is centred.
    const scale = 20;
    const picture = new Image();
    picture.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
      drawing('0 0 96 96', strip(cut), glyph('#000')).replace('<svg ', `<svg width="${96 * scale}" height="${96 * scale}" `),
    )}`;
    await picture.decode();
    const canvas = Object.assign(document.createElement('canvas'), { width: 96 * scale, height: 96 * scale });
    const context = canvas.getContext('2d');
    context.drawImage(picture, 0, 0);
    const alpha = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let [left, top, right, bottom] = [canvas.width, canvas.height, -1, -1];
    for (let row = 0; row < canvas.height; row++) {
      for (let column = 0; column < canvas.width; column++) {
        if (alpha[(row * canvas.width + column) * 4 + 3] > 8) {
          left = Math.min(left, column);
          right = Math.max(right, column + 1);
          top = Math.min(top, row);
          bottom = Math.max(bottom, row + 1);
        }
      }
    }
    const side = Math.ceil(Math.max(right - left, bottom - top) / scale) + 3;
    const frame = [(left + right) / 2 / scale - side / 2, (top + bottom) / 2 / scale - side / 2, side, side].map(
      (value) => Math.round(value * 2) / 2,
    );
    const framed = frame.join(' ');
    const symbol = (colour) => drawing(framed, strip(cut), glyph(colour));
    const favicon = drawing(
      framed,
      `${strip(cut)}<style>@media (prefers-color-scheme: dark){g{stroke:${inverse}}}</style>`,
      glyph(ink),
    );
    const badge = drawing(framed, strip(cut), glyph('#fff'));

    const placed = tile.querySelector('use').parentNode;
    const [, tx, ty, tileScale] = placed
      .getAttribute('transform')
      .match(/translate\(([-\d.]+) ([-\d.]+)\) scale\(([\d.]+)\)/)
      .map(Number);
    const tileInk = placed.getAttribute('stroke');
    const arc = tile.querySelector('path');
    const [from, to] = [...fill.querySelectorAll('stop')].map((stop) => stop.getAttribute('stop-color'));
    const tiled = ({ rounded, content = 1 }) => {
      const background = tile.querySelector('rect').cloneNode();
      if (!rounded) background.removeAttribute('rx');
      let inside = `${strip(arc)}<g transform="translate(${tx} ${ty}) scale(${tileScale})">${glyph(tileInk)}</g>`;
      if (content !== 1) inside = `<g transform="translate(48 48) scale(${content}) translate(-48 -48)">${inside}</g>`;
      return drawing('0 0 96 96', strip(cut) + strip(fill), strip(background) + inside);
    };

    // VectorDrawable has no mask: the cut becomes a clip, its two edges run on to the top of the glyph box,
    // above the stroke's ink.
    const corners = cut
      .querySelector('path')
      .getAttribute('d')
      .match(/[-\d.]+/g)
      .map(Number);
    const [ax, ay, run] = corners;
    const [cx, cy, dx] = corners.slice(3);
    const atTop = (x1, y1, x2, y2) => x1 + ((x2 - x1) * -y1) / (y2 - y1);
    const clip = `M0,0H${atTop(ax, ay, dx, cy)}L${dx},${cy}H${cx}L${atTop(ax + run, ay, cx, cy)},0H96V96H0Z`;

    return {
      size: [width, height],
      origin: [x, y],
      files: {
        'logo.svg': logo(ink),
        'logo-inverse.svg': logo(inverse),
        'mark.svg': symbol(ink),
        'mark-inverse.svg': symbol(inverse),
        'favicon.svg': favicon,
      },
      favicon: symbol(ink),
      badge,
      tile: tiled({ rounded: true }),
      square: tiled({ rounded: false }),
      // A launcher keeps the centred circle of 80 % of a maskable icon's side; the glyph's corner would touch it.
      maskable: tiled({ rounded: false, content: 0.9 }),
      vector: {
        glyph: mark.getAttribute('d'),
        pen: Object.fromEntries(['stroke-width', 'stroke-linecap', 'stroke-linejoin'].map((name) => [name, wordmark.getAttribute(name)])),
        clip,
        frame,
        ink,
        inverse,
        tile: { from, to, ink: tileInk, x: tx, y: ty, scale: tileScale, arc: arc.getAttribute('d'), opacity: arc.getAttribute('stroke-opacity'), arcWidth: arc.getAttribute('stroke-width') },
      },
    };
  }, master);

  await mkdir(output, { recursive: true });
  for (const [name, content] of Object.entries(brand.files)) await writeFile(resolve(output, name), `${content}\n`);
  async function png(svg, width, height = width) {
    await page.setViewportSize({ width, height });
    await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:100vw;height:100vh}</style>${svg}`);
    return page.screenshot({ omitBackground: true });
  }
  for (const size of [192, 512]) await writeFile(resolve(output, `icon-${size}.png`), await png(brand.tile, size));
  // iOS rounds the corners itself and puts black behind transparency.
  await writeFile(resolve(output, 'icon-180.png'), await png(brand.square, 180));
  await writeFile(resolve(output, 'icon-maskable-512.png'), await png(brand.maskable, 512));
  // Android paints a notification badge in one colour from its alpha alone.
  await writeFile(resolve(output, 'badge-96.png'), await png(brand.badge, 96));
  const sizes = [16, 32, 48, 64];
  const images = [];
  for (const size of sizes) images.push(await png(brand.favicon, size));
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

  const { glyph, pen, clip, frame, ink, inverse, tile } = brand.vector;
  const vector = (size, viewport, body, gradient = false) =>
    `<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"${gradient ? '\n    xmlns:aapt="http://schemas.android.com/aapt"' : ''}
    android:width="${size}dp"
    android:height="${size}dp"
    android:viewportWidth="${viewport}"
    android:viewportHeight="${viewport}">
${body}</vector>
`;
  const stroke = (colour, indent) => `${indent}<path
${indent}    android:pathData="${glyph}"
${indent}    android:strokeColor="${colour}"
${indent}    android:strokeWidth="${pen['stroke-width']}"
${indent}    android:strokeLineCap="${pen['stroke-linecap']}"
${indent}    android:strokeLineJoin="${pen['stroke-linejoin']}" />
`;
  const letter = (colour) => `    <group
        android:translateX="${-frame[0]}"
        android:translateY="${-frame[1]}">
        <clip-path android:pathData="${clip}" />
${stroke(colour, '        ')}    </group>
`;
  // An adaptive icon shows 72 of its 108 dp: the 96-unit tile fills those 72.
  const shown = (value) => +(18 + 0.75 * value).toFixed(3);
  const files = {
    'drawable/launcher_background.xml': vector(108, 108, `    <path android:pathData="M0,0h108v108h-108z">
        <aapt:attr name="android:fillColor">
            <gradient
                android:type="linear"
                android:startX="18"
                android:startY="18"
                android:endX="90"
                android:endY="90">
                <item android:offset="0" android:color="${tile.from}" />
                <item android:offset="1" android:color="${tile.to}" />
            </gradient>
        </aapt:attr>
    </path>
    <group
        android:translateX="18"
        android:translateY="18"
        android:scaleX="0.75"
        android:scaleY="0.75">
        <path
            android:pathData="${tile.arc}"
            android:strokeColor="#FFFFFF"
            android:strokeAlpha="${tile.opacity}"
            android:strokeWidth="${tile.arcWidth}" />
    </group>
`, true),
    'drawable/launcher_foreground.xml': vector(108, 108, `    <group
        android:translateX="${shown(tile.x)}"
        android:translateY="${shown(tile.y)}"
        android:scaleX="${+(0.75 * tile.scale).toFixed(3)}"
        android:scaleY="${+(0.75 * tile.scale).toFixed(3)}">
        <clip-path android:pathData="${clip}" />
${stroke(tile.ink, '        ')}    </group>
`),
    'drawable/brand_mark.xml': vector(72, frame[2], letter('@color/brand')),
    'drawable/brand_badge.xml': vector(24, frame[2], letter('#FFFFFF')),
    'values/brand.xml': `<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="brand">${ink}</color>\n</resources>\n`,
    'values-night/brand.xml': `<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="brand">${inverse}</color>\n</resources>\n`,
  };
  for (const [name, content] of Object.entries(files)) {
    await mkdir(resolve(android, name, '..'), { recursive: true });
    await writeFile(resolve(android, name), content);
  }
} finally {
  await browser.close();
}
console.log(`Brand assets written to ${output} and ${android}`);
