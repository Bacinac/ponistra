// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { keepView, viewFor } from './views';

describe('the view a document opens in', () => {
  beforeEach(() => localStorage.clear());

  it('is the view of what it came from, else its pages', () => {
    keepView('notes', 'text');
    expect([
      viewFor('deck', 'pptx'),
      viewFor('book', 'xlsx'),
      viewFor('offer', 'docx'),
      viewFor('new', null),
    ]).toEqual(['slides', 'text', 'pages', 'pages']);
  });

  it('is the one its reader chose for it', () => {
    keepView('deck', 'text');
    keepView('notes', 'slides');
    expect([viewFor('deck', 'pptx'), viewFor('notes', null)]).toEqual(['text', 'slides']);
  });

  it('is its pages when what the browser keeps is not a view', () => {
    keepView('offer', 'text');
    localStorage.setItem('ponistra.views', 'null');
    expect(viewFor('offer', null)).toBe('pages');
  });
});
