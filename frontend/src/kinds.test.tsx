// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { heldKind } from './kinds';

describe('heldKind', () => {
  it('tells the kind by the bytes, the name only within plain text', () => {
    expect(heldKind('image/tiff', 'tif')).toBe('picture');
    expect(heldKind('application/x-7z-compressed', null)).toBe('archive');
    expect(heldKind('application/vnd.ms-outlook', 'msg')).toBe('message');
    expect(heldKind('text/vcard', 'txt')).toBe('cards');
    expect(heldKind('text/calendar', null)).toBe('events');
    expect(heldKind('text/plain', 'EML')).toBe('message');
    expect(heldKind('text/plain', 'md')).toBe('markdown');
    expect(heldKind('text/plain', 'txt')).toBeNull();
    expect(heldKind('application/pdf', 'zip')).toBeNull();
    expect(heldKind(null, 'zip')).toBeNull();
  });
});
