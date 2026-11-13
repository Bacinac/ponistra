// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { keepView, viewFor } from './views';

describe('the view a document opens in', () => {
  beforeEach(() => localStorage.clear());

  it('is the form of the file it came from, until its reader chooses another', () => {
    keepView('notes', 'text');
    expect([viewFor('deck', 'pptx'), viewFor('offer', 'docx'), viewFor('prices', 'xlsx')]).toEqual([
      'slides',
      'pages',
      'text',
    ]);
    keepView('deck', 'text');
    keepView('offer', 'text');
    expect([viewFor('deck', 'pptx'), viewFor('offer', 'docx')]).toEqual(['text', 'text']);
  });

  it('is the one its reader chose for it, else the one they chose last for any', () => {
    expect(viewFor('notes', null)).toBe('text');
    keepView('notes', 'pages');
    keepView('plan', 'text');
    expect([viewFor('notes', null), viewFor('plan', null), viewFor('new', null)]).toEqual([
      'pages',
      'text',
      'text',
    ]);
  });

  it('falls back on the reader’s last choice when what the browser keeps is not a view', () => {
    keepView('offer', 'pages');
    localStorage.setItem('ponistra.views', 'null');
    expect(viewFor('offer', null)).toBe('pages');
  });
});
