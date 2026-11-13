import { zipped } from './zip';

const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
const R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const PACKAGE = 'http://schemas.openxmlformats.org/package/2006';
const WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml';
export const DOCX = `${WORD}.document`;

const run = (text: string) => `<w:r><w:t xml:space="preserve">${text}</w:t></w:r>`;
const counted = (instruction: string) =>
  `<w:fldSimple w:instr=" ${instruction} ">${run('1')}</w:fldSimple>`;

/** A Word file of two pages, the second after a page break, each headed with its number. */
export function wordFile(): Buffer {
  return headed(
    `<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>${run('Ugovor')}</w:p>` +
      `<w:p>${run('Prvi članak')}</w:p>` +
      '<w:p><w:r><w:br w:type="page"/></w:r></w:p>' +
      `<w:p>${run('Drugi članak')}</w:p>`,
  );
}

/** A Word file of one paragraph: `text`, `breaks` line breaks and `last`. */
export function wordLines(text: string, breaks: number, last: string): Buffer {
  return headed(`<w:p>${run(text)}${'<w:r><w:br/></w:r>'.repeat(breaks)}${run(last)}</w:p>`);
}

function headed(paragraphs: string): Buffer {
  const body =
    paragraphs +
    '<w:sectPr><w:headerReference w:type="default" r:id="rIdheader"/>' +
    '<w:pgSz w:w="11906" w:h="16838"/></w:sectPr>';
  const header = `<w:p>${run('Stranica ')}${counted('PAGE')}${run(' od ')}${counted('NUMPAGES')}</w:p>`;
  return zipped({
    '[Content_Types].xml':
      `<Types xmlns="${PACKAGE}/content-types">` +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      `<Override PartName="/word/document.xml" ContentType="${DOCX}.main+xml"/>` +
      `<Override PartName="/word/header.xml" ContentType="${WORD}.header+xml"/></Types>`,
    '_rels/.rels':
      `<Relationships xmlns="${PACKAGE}/relationships"><Relationship Id="rId1" ` +
      `Type="${R}/officeDocument" Target="word/document.xml"/></Relationships>`,
    'word/_rels/document.xml.rels':
      `<Relationships xmlns="${PACKAGE}/relationships">` +
      `<Relationship Id="rIdheader" Type="${R}/header" Target="header.xml"/></Relationships>`,
    'word/document.xml': `<w:document xmlns:w="${W}" xmlns:r="${R}"><w:body>${body}</w:body></w:document>`,
    'word/header.xml': `<w:hdr xmlns:w="${W}" xmlns:r="${R}">${header}</w:hdr>`,
  });
}
