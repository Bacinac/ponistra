// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { forTheServer, ledTo } from './launch';

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
