// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { forTheServer, ledTo, onlyPdfs } from './launch';

describe('ledTo', () => {
  it('leads to the address a launch asks for, with its query', () => {
    expect(ledTo('https://ponistra.example/mail?mailto=mailto%3Aana%40x.hr', '/d/ugovor')).toBe(
      '/mail?mailto=mailto%3Aana%40x.hr',
    );
    expect(ledTo('https://ponistra.example/notes?new', '/')).toBe('/notes?new');
  });

  it('leaves the window where it is for the start of the app and where it is already', () => {
    expect(ledTo('https://ponistra.example/', '/d/ugovor')).toBeNull();
    expect(ledTo('https://ponistra.example/documents', '/documents')).toBeNull();
    expect(ledTo(undefined, '/')).toBeNull();
  });
});

describe('forTheServer', () => {
  it('knows the addresses the server answers from the pages of the app', () => {
    for (const path of [
      '/api/agents/authorize?client_id=x',
      '/dav/ana/',
      '/android/ponistra.apk',
      '/.well-known/oauth-authorization-server',
    ])
      expect(forTheServer(path)).toBe(true);
    for (const path of ['/', '/mail?mailto=x', '/agents/consent?request=x', '/api-notes', '/davor'])
      expect(forTheServer(path)).toBe(false);
  });
});

describe('onlyPdfs', () => {
  const file = (name: string, type: string) => new File(['%PDF'], name, { type });

  it('takes a launch whose every file is a PDF, by its type or its name', () => {
    expect(onlyPdfs({ files: [file('a.pdf', 'application/pdf')] })).toBe(true);
    expect(onlyPdfs({ files: [file('B.PDF', ''), file('c.pdf', 'application/pdf')] })).toBe(true);
  });

  it('leaves a launch with any other file, or with none, to someone signed in', () => {
    expect(onlyPdfs({ files: [file('a.pdf', 'application/pdf'), file('b.docx', '')] })).toBe(false);
    expect(onlyPdfs({ files: [], target: 'https://ponistra.example/mail' })).toBe(false);
  });
});
