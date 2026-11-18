import { afterEach, describe, expect, it, vi } from 'vitest';
import { clipboardHeld } from './clipboard';

function stubClipboard(...answers: (string | Error)[]) {
  const read = vi.fn();
  for (const answer of answers) {
    if (answer instanceof Error) read.mockRejectedValueOnce(answer);
    else
      read.mockResolvedValueOnce(
        answer ? [{ types: ['text/plain'], getType: async () => new Blob([answer]) }] : [],
      );
  }
  vi.stubGlobal('navigator', { clipboard: { read } });
  return read;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('clipboardHeld', () => {
  it('reads again when the first read finds nothing or is refused', async () => {
    vi.useFakeTimers();
    const read = stubClipboard('', new Error('Document is not focused.'), 'ls -la');
    const held = clipboardHeld();
    await vi.runAllTimersAsync();
    expect(await held).toEqual({ text: 'ls -la', files: [] });
    expect(read).toHaveBeenCalledTimes(3);
  });

  it('gives an empty clipboard up after its last read', async () => {
    vi.useFakeTimers();
    const read = stubClipboard('', '', '', '');
    const held = clipboardHeld();
    await vi.runAllTimersAsync();
    expect(await held).toEqual({ text: '', files: [] });
    expect(read).toHaveBeenCalledTimes(4);
  });

  it('fails with the last refusal', async () => {
    vi.useFakeTimers();
    const refused = new Error('NotAllowedError');
    stubClipboard(refused, refused, refused, refused);
    const held = clipboardHeld();
    const failed = expect(held).rejects.toBe(refused);
    await vi.runAllTimersAsync();
    await failed;
  });
});
