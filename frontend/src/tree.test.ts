import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import { en } from './i18n/en';
import { hr, type MessageKey } from './i18n/hr';
import { errorMessage, stepTitle } from './tree';

const t = (key: MessageKey) => hr[key];

describe('errorMessage', () => {
  it('speaks the server error code', () => {
    expect(errorMessage(new ApiError('/api/nodes/1', 400, 'cycle'), t)).toBe(hr['error.cycle']);
  });

  it('treats a bare 404 as a missing item', () => {
    expect(errorMessage(new ApiError('/api/nodes/x', 404, undefined), t)).toBe(
      hr['error.not_found'],
    );
  });

  it("treats a bare 413 as a file too large, as Cloudflare's own page answers", () => {
    expect(errorMessage(new ApiError('/api/blobs', 413, undefined), t)).toBe(hr['error.too_large']);
  });

  it('falls back to the raw message for an unknown failure', () => {
    const message = errorMessage(new ApiError('/api/nodes', 500, undefined), t);
    expect(message).toBe(`${hr['error.unexpected']}: /api/nodes: HTTP 500`);
  });
});

describe('a place of the user’s own', () => {
  const english = (key: MessageKey) => en[key];
  const step = { title: 'Poveznice', notes: false, links: true, boards: false };

  it('goes by the interface’s name whatever the title it was made under', () => {
    expect(stepTitle(step, english)).toBe('Links');
    expect(stepTitle({ ...step, links: false, notes: true }, english)).toBe('Notes');
    expect(stepTitle({ ...step, links: false, boards: true }, english)).toBe('Boards');
  });

  it('leaves a folder the user named as it is', () => {
    expect(stepTitle({ ...step, title: 'Posao', links: false }, english)).toBe('Posao');
  });
});
