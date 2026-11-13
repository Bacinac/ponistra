// @vitest-environment jsdom
import { EditorState } from 'prosemirror-state';
import { describe, expect, it } from 'vitest';
import { mailDoc, mailHtml, opening, resign } from './mailText';

const BLOB = 'a'.repeat(64);
const work = `<p>Ivo</p><p><strong>Brezik</strong></p><p><img src="/api/mail/inline/${BLOB}" alt="logo"></p>`;
const home = '<p>Ivo</p>';

describe('opening', () => {
  it('writes each line of the text given, an empty line and the signature', () => {
    expect(mailHtml(opening('Bok\nkako si', home))).toBe(
      '<p>Bok</p><p>kako si</p><p></p><div data-signature=""><p>Ivo</p></div>',
    );
  });

  it('leaves out a signature with nothing in it', () => {
    expect(mailHtml(opening('', '<p> </p>'))).toBe('<p></p>');
  });
});

describe('resign', () => {
  const state = (signed: string) => EditorState.create({ doc: opening('Bok', signed) });

  it('puts the new account’s signature in place of the one before', () => {
    expect(mailHtml(resign(state(work), home).doc)).toBe(
      '<p>Bok</p><p></p><div data-signature=""><p>Ivo</p></div>',
    );
  });

  it('takes the signature out for an account without one', () => {
    expect(mailHtml(resign(state(work), '').doc)).toBe('<p>Bok</p><p></p>');
  });

  it('puts a signature at the end where there was none', () => {
    expect(mailHtml(resign(state(''), work).doc)).toBe(
      `<p>Bok</p><p></p><div data-signature="">${work}</div>`,
    );
  });
});

describe('mailDoc', () => {
  it('keeps the palette’s colours, links and PONISTRA’s images, nothing else', () => {
    const doc = mailDoc(
      '<p><span style="color: #c4321c">crveno</span> <span style="color: #123456">ne</span> ' +
        '<a href="https://primjer.hr">veza</a><img src="https://drugdje.hr/a.png"></p>',
    );
    const html = mailHtml(doc);
    expect(html).toContain('<span style="color: rgb(196, 50, 28);">crveno</span>');
    expect(html).toContain('<a href="https://primjer.hr">veza</a>');
    expect(html).not.toContain('#123456');
    expect(html).not.toContain('drugdje');
  });

  it('reads a font by its name or ours that stands for it, and a size in points', () => {
    const html = mailHtml(
      mailDoc(
        '<p><span style="font-family: Carlito, sans-serif; font-size: 16px">a</span>' +
          '<span style="font-family: Comic Sans MS; font-size: 13pt">b</span></p>',
      ),
    );
    expect(html).toContain('font-family: &quot;Calibri&quot;, &quot;Carlito&quot;, sans-serif');
    expect(html).toContain('font-size: 12pt');
    expect(html).toContain('font-size: 12pt;">b');
    expect(html).not.toContain('Comic');
  });

  it('keeps a line spacing of those offered, none for the usual', () => {
    expect(
      mailHtml(mailDoc('<p style="line-height: 150%">a</p><p style="line-height: 1.2">b</p>')),
    ).toBe('<p style="line-height: 1.5;">a</p><p>b</p>');
  });
});
