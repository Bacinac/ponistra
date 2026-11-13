import { createCipheriv, createHash, randomBytes } from 'node:crypto';
import type { Page } from '@playwright/test';

const WIDTH = 595;
const HEIGHT = 842;

/** A line of Helvetica, `top` points below the page's top edge. */
export interface Line {
  text: string;
  top: number;
}

/** A note pinned to a page, which readers show as an icon that opens its text. */
export interface Note {
  page: number;
  left: number;
  top: number;
  text: string;
  author: string;
}

/** A form field's box, `top` points below the page's top edge. */
interface Box {
  page: number;
  left: number;
  top: number;
  width: number;
  height?: number;
}

/** A form field: text, which a script may check as a number with a comma and reckon as the sum of
 * others; a box ticked to its state; a radio group, its options side by side; a list that drops
 * down; or a place to sign. */
export type Field = Box & { name: string } & (
    | { kind: 'text'; value?: string; number?: boolean; sum?: string[] }
    | { kind: 'check'; on: string }
    | { kind: 'radio'; options: string[] }
    | { kind: 'combo'; options: string[] }
    | { kind: 'signature' }
  );

export interface Bookmark {
  title: string;
  page: number;
  top: number;
  under?: Bookmark[];
}

interface Made {
  pages: Line[][];
  bookmarks?: Bookmark[];
  notes?: Note[];
  fields?: Field[];
  /** Bytes each page's drawing is padded to, so that fetching one page is told from fetching all. */
  padding?: number;
  /** Given, the file is encrypted with AES-256 (revision 5) and opens only with it. */
  password?: string;
}

const literal = (text: string) => `(${text.replace(/[\\()]/g, '\\$&')})`;
const unicode = (text: string) =>
  `<FEFF${[...text].map((char) => char.charCodeAt(0).toString(16).padStart(4, '0')).join('')}>`;
const hex = (bytes: Buffer) => `<${bytes.toString('hex')}>`;
const sha256 = (...parts: Buffer[]) => createHash('sha256').update(Buffer.concat(parts)).digest();

function aes(key: Buffer, data: Buffer, iv: Buffer | null, padded: boolean): Buffer {
  const cipher = createCipheriv(iv ? 'aes-256-cbc' : 'aes-256-ecb', key, iv);
  cipher.setAutoPadding(padded);
  return Buffer.concat([cipher.update(data), cipher.final()]);
}

/** The Standard security handler's entries for a key opened by `password`, as ISO 32000 extension
 * level 3 (AES-256, revision 5) defines them; the owner's password is the same. */
function secured(key: Buffer, password: string): string {
  const typed = Buffer.from(password, 'utf8');
  const [userCheck, userKey, ownerCheck, ownerKey] = [0, 1, 2, 3].map(() => randomBytes(8));
  const u = Buffer.concat([sha256(typed, userCheck), userCheck, userKey]);
  const ue = aes(sha256(typed, userKey), key, Buffer.alloc(16), false);
  const o = Buffer.concat([sha256(typed, ownerCheck, u), ownerCheck, ownerKey]);
  const oe = aes(sha256(typed, ownerKey, u), key, Buffer.alloc(16), false);
  const permissions = Buffer.alloc(16);
  permissions.writeInt32LE(-4, 0);
  permissions.writeInt32LE(-1, 4);
  permissions.write('Tadb', 8, 'latin1');
  const perms = aes(key, permissions, null, false);
  return (
    '<< /Filter /Standard /V 5 /R 5 /Length 256 /P -4 ' +
    '/CF << /StdCF << /AuthEvent /DocOpen /CFM /AESV3 /Length 32 >> >> /StmF /StdCF /StrF /StdCF ' +
    `/U ${hex(u)} /UE ${hex(ue)} /O ${hex(o)} /OE ${hex(oe)} /Perms ${hex(perms)} >>`
  );
}

/** A PDF of A4 pages written by hand: every dictionary first, then the pages' drawings, as a
 * reader that fetches only the parts it shows would want them. */
export function pdfFile({
  pages,
  bookmarks = [],
  notes = [],
  fields = [],
  padding = 0,
  password,
}: Made): Buffer {
  const bodies: (string | Buffer)[] = [];
  const reserve = () => bodies.push('');
  const key = password ? randomBytes(32) : null;
  const look = (drawn: string) =>
    `<< /Type /XObject /Subtype /Form /BBox [0 0 16 16] /Length ${drawn.length} >>\n` +
    `stream\n${drawn}\nendstream`;
  const stream = (data: string) => {
    const bytes = Buffer.from(data, 'latin1');
    const iv = randomBytes(16);
    const sealed = key ? Buffer.concat([iv, aes(key, bytes, iv, true)]) : bytes;
    return Buffer.concat([
      Buffer.from(`<< /Length ${sealed.length} >>\nstream\n`, 'latin1'),
      sealed,
      Buffer.from('\nendstream', 'latin1'),
    ]);
  };
  if (key && (bookmarks.length || notes.length || fields.length)) {
    throw new Error('an encrypted file here has neither bookmarks, notes nor fields');
  }

  const catalog = reserve();
  const tree = reserve();
  const font = reserve();
  const outlines = bookmarks.length ? reserve() : null;
  const pageIds = pages.map(() => reserve());
  const flat: { mark: Bookmark; id: number; parent: number; siblings: Bookmark[] }[] = [];
  const number = (marks: Bookmark[], parent: number) => {
    for (const mark of marks) {
      flat.push({ mark, id: reserve(), parent, siblings: marks });
      number(mark.under ?? [], flat.at(-1)!.id);
    }
  };
  if (outlines) number(bookmarks, outlines);
  const idOf = (mark: Bookmark) => flat.find((each) => each.mark === mark)!.id;
  const noteIds = notes.map(() => reserve());
  const form = fields.length ? reserve() : null;
  const looks = fields.length ? { on: reserve(), off: reserve() } : null;
  const fieldIds = fields.map(() => reserve());
  const widgetIds = fields.map((each) => (each.kind === 'radio' ? each.options.map(reserve) : []));
  const contents = pages.map(() => reserve());

  bodies[catalog - 1] =
    `<< /Type /Catalog /Pages ${tree} 0 R` +
    (outlines ? ` /Outlines ${outlines} 0 R` : '') +
    (form ? ` /AcroForm ${form} 0 R >>` : ' >>');
  bodies[tree - 1] =
    `<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(' ')}] /Count ${pages.length} >>`;
  bodies[font - 1] =
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
  if (outlines) {
    bodies[outlines - 1] =
      `<< /Type /Outlines /First ${idOf(bookmarks[0])} 0 R ` +
      `/Last ${idOf(bookmarks.at(-1)!)} 0 R /Count ${flat.length} >>`;
  }
  for (const { mark, id, parent, siblings } of flat) {
    const index = siblings.indexOf(mark);
    const under = mark.under ?? [];
    const links = [
      `/Parent ${parent} 0 R`,
      index > 0 ? `/Prev ${idOf(siblings[index - 1])} 0 R` : '',
      index < siblings.length - 1 ? `/Next ${idOf(siblings[index + 1])} 0 R` : '',
      under.length
        ? `/First ${idOf(under[0])} 0 R /Last ${idOf(under.at(-1)!)} 0 R /Count ${under.length}`
        : '',
    ];
    bodies[id - 1] =
      `<< /Title ${unicode(mark.title)} ${links.filter(Boolean).join(' ')} ` +
      `/Dest [${pageIds[mark.page - 1]} 0 R /XYZ 0 ${HEIGHT - mark.top} null] >>`;
  }
  notes.forEach(({ page, left, top, text, author }, index) => {
    const bottom = HEIGHT - top - 20;
    bodies[noteIds[index] - 1] =
      `<< /Type /Annot /Subtype /Text /Name /Comment /P ${pageIds[page - 1]} 0 R ` +
      `/Rect [${left} ${bottom} ${left + 20} ${bottom + 20}] /Contents ${unicode(text)} ` +
      `/T ${unicode(author)} /M (D:20261019120000+02'00') >>`;
  });
  if (form && looks) {
    const sums = fields.flatMap((each, at) => (each.kind === 'text' && each.sum ? [at] : []));
    bodies[form - 1] =
      `<< /Fields [${fieldIds.map((id) => `${id} 0 R`).join(' ')}] ` +
      `/DR << /Font << /Helv ${font} 0 R >> >> /DA (/Helv 0 Tf 0 g)` +
      (sums.length ? ` /CO [${sums.map((at) => `${fieldIds[at]} 0 R`).join(' ')}] >>` : ' >>');
    bodies[looks.on - 1] = look('0 g 3 3 10 10 re f');
    bodies[looks.off - 1] = look('');
  }
  const rectOf = ({ page, left, top, width, height = 20 }: Box) =>
    `/P ${pageIds[page - 1]} 0 R /Rect [${left} ${HEIGHT - top - height} ${left + width} ${HEIGHT - top}]`;
  const states = (on: string) =>
    `/AP << /N << /${on} ${looks!.on} 0 R /Off ${looks!.off} 0 R >> >> /AS /Off`;
  const script = (code: string) => `<< /S /JavaScript /JS ${literal(code)} >>`;
  fields.forEach((each, at) => {
    const widget = `/Type /Annot /Subtype /Widget /F 4 /T ${unicode(each.name)} ${rectOf(each)}`;
    const typed = '/DA (/Helv 12 Tf 0 g)';
    if (each.kind === 'text') {
      const number = 'AFNumber_Keystroke(2, 2, 0, 0, "", true);';
      const shown = 'AFNumber_Format(2, 2, 0, 0, "", true);';
      const sum =
        each.sum &&
        `AFSimple_Calculate("SUM", new Array(${each.sum.map((name) => `"${name}"`).join(', ')}));`;
      const actions = [
        each.number ? `/K ${script(number)} /F ${script(shown)}` : '',
        sum ? `/C ${script(sum)}` : '',
      ].join(' ');
      bodies[fieldIds[at] - 1] =
        `<< ${widget} /FT /Tx ${typed}` +
        (each.sum ? ' /Ff 1' : '') +
        (each.value ? ` /V ${unicode(each.value)}` : '') +
        (actions.trim() ? ` /AA << ${actions} >> >>` : ' >>');
    } else if (each.kind === 'check') {
      bodies[fieldIds[at] - 1] = `<< ${widget} /FT /Btn /V /Off ${states(each.on)} >>`;
    } else if (each.kind === 'combo') {
      bodies[fieldIds[at] - 1] =
        `<< ${widget} /FT /Ch /Ff 131072 ${typed} ` +
        `/Opt [${each.options.map(unicode).join(' ')}] >>`;
    } else if (each.kind === 'signature') {
      bodies[fieldIds[at] - 1] = `<< ${widget} /FT /Sig >>`;
    } else {
      bodies[fieldIds[at] - 1] =
        `<< /FT /Btn /Ff 49152 /T ${unicode(each.name)} /V /Off ` +
        `/Kids [${widgetIds[at].map((id) => `${id} 0 R`).join(' ')}] >>`;
      each.options.forEach((option, index) => {
        const box = { ...each, left: each.left + index * (each.width + 10) };
        bodies[widgetIds[at][index] - 1] =
          `<< /Type /Annot /Subtype /Widget /F 4 /Parent ${fieldIds[at]} 0 R ${rectOf(box)} ` +
          `${states(option)} >>`;
      });
    }
  });
  pages.forEach((lines, index) => {
    const pinned = [
      ...noteIds.filter((_, at) => notes[at].page === index + 1),
      ...fields.flatMap((each, at) =>
        each.page !== index + 1 ? [] : each.kind === 'radio' ? widgetIds[at] : [fieldIds[at]],
      ),
    ];
    const annots = pinned.length ? ` /Annots [${pinned.map((id) => `${id} 0 R`).join(' ')}]` : '';
    bodies[pageIds[index] - 1] =
      `<< /Type /Page /Parent ${tree} 0 R /MediaBox [0 0 ${WIDTH} ${HEIGHT}] ` +
      `/Resources << /Font << /F1 ${font} 0 R >> >> /Contents ${contents[index]} 0 R${annots} >>`;
    let drawn = lines
      .map(({ text, top }) => `BT /F1 14 Tf 72 ${HEIGHT - top} Td ${literal(text)} Tj ET\n`)
      .join('');
    while (drawn.length < padding) drawn += `% ${'x'.repeat(97)}\n`;
    bodies[contents[index] - 1] = stream(drawn);
  });
  const encrypt = key ? reserve() : null;
  if (encrypt) bodies[encrypt - 1] = secured(key!, password!);
  return assembled(bodies, catalog, encrypt);
}

/** Pages that are only pictures of text, as a scanner makes them; signed, the file says it
 * carries a signature, as a scan signed after it was made does. */
export function scannedFile(jpegs: Buffer[], signed = false): Buffer {
  const pageIds = jpegs.map((_, index) => 3 + 3 * index);
  return assembled(
    [
      '<< /Type /Catalog /Pages 2 0 R' +
        (signed ? ' /AcroForm << /Fields [] /SigFlags 3 >> >>' : ' >>'),
      `<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(' ')}] /Count ${jpegs.length} >>`,
      ...jpegs.flatMap((jpeg, index) => {
        const frame = jpeg.indexOf(Buffer.from([0xff, 0xc0]));
        const drawn = `q ${WIDTH} 0 0 ${HEIGHT} 0 0 cm /Scan Do Q`;
        return [
          `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${WIDTH} ${HEIGHT}] ` +
            `/Resources << /XObject << /Scan ${pageIds[index] + 1} 0 R >> >> ` +
            `/Contents ${pageIds[index] + 2} 0 R >>`,
          Buffer.concat([
            Buffer.from(
              `<< /Type /XObject /Subtype /Image /Width ${jpeg.readUInt16BE(frame + 7)} ` +
                `/Height ${jpeg.readUInt16BE(frame + 5)} /ColorSpace /DeviceRGB ` +
                `/BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`,
              'latin1',
            ),
            jpeg,
            Buffer.from('\nendstream', 'latin1'),
          ]),
          `<< /Length ${drawn.length} >>\nstream\n${drawn}\nendstream`,
        ];
      }),
    ],
    1,
    null,
  );
}

function assembled(bodies: (string | Buffer)[], catalog: number, encrypt: number | null): Buffer {
  const parts: Buffer[] = [Buffer.from('%PDF-1.7\n%\xe2\xe3\xcf\xd3\n', 'latin1')];
  let at = parts[0].length;
  const offsets: number[] = [];
  bodies.forEach((body, index) => {
    offsets.push(at);
    const object = Buffer.concat([
      Buffer.from(`${index + 1} 0 obj\n`, 'latin1'),
      typeof body === 'string' ? Buffer.from(body, 'latin1') : body,
      Buffer.from('\nendobj\n', 'latin1'),
    ]);
    parts.push(object);
    at += object.length;
  });
  const id = hex(randomBytes(16));
  parts.push(
    Buffer.from(
      `xref\n0 ${bodies.length + 1}\n0000000000 65535 f \n` +
        offsets.map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`).join('') +
        `trailer\n<< /Size ${bodies.length + 1} /Root ${catalog} 0 R /ID [${id} ${id}]` +
        (encrypt ? ` /Encrypt ${encrypt} 0 R >>` : ' >>') +
        `\nstartxref\n${at}\n%%EOF\n`,
      'latin1',
    ),
  );
  return Buffer.concat(parts);
}

/** Uploads the file to the root and opens it. */
export async function upload(page: Page, title: string, buffer: Buffer): Promise<void> {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: `${title}.pdf`, mimeType: 'application/pdf', buffer });
  await page
    .getByRole('row', { name: new RegExp(title) })
    .getByText(title, { exact: true })
    .dblclick();
}

export const pageAt = (page: Page, number: number) =>
  page.locator(`.pdfViewer .page[data-page-number="${number}"]`);
