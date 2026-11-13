// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const version = vi.fn();
vi.mock('./api', () => ({ getJson: () => version() }));

async function fresh() {
  vi.resetModules();
  return import('./release');
}

describe('release', () => {
  const reload = vi.fn();

  beforeEach(() => {
    reload.mockClear();
    version.mockReset();
    sessionStorage.clear();
    vi.stubGlobal('location', { reload });
  });

  it('stays while the server runs the release the page came with', async () => {
    const { heardRelease, takeNewRelease } = await fresh();
    heardRelease('1');
    heardRelease('1');
    takeNewRelease();
    expect(reload).not.toHaveBeenCalled();
  });

  it('takes a new release at the next page, once', async () => {
    const { heardRelease, takeNewRelease } = await fresh();
    heardRelease('1');
    heardRelease('2');
    takeNewRelease();
    takeNewRelease();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('waits for work that goes on across pages', async () => {
    const { heardRelease, takeNewRelease, useHeldRelease } = await fresh();
    heardRelease('1');
    heardRelease('2');
    const { unmount } = renderHook(() => useHeldRelease(true));
    takeNewRelease();
    expect(reload).not.toHaveBeenCalled();
    unmount();
    takeNewRelease();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  describe('out of sight', () => {
    let hidden = false;
    let followed = () => {};

    beforeEach(() => {
      hidden = false;
      vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
      document.body.innerHTML = '';
    });

    afterEach(() => {
      followed();
      vi.restoreAllMocks();
    });

    async function following() {
      const release = await fresh();
      followed = release.followPage();
      release.heardRelease('1');
      return release;
    }

    function away() {
      hidden = true;
      document.dispatchEvent(new Event('visibilitychange'));
    }

    function typedInto(field: HTMLInputElement | HTMLTextAreaElement, text: string) {
      field.value = text;
      field.dispatchEvent(new InputEvent('input', { bubbles: true }));
    }

    it('a page that stays takes a new release as it goes out of sight', async () => {
      const { heardRelease } = await following();
      heardRelease('2');
      expect(reload).not.toHaveBeenCalled();
      away();
      expect(reload).toHaveBeenCalledTimes(1);
    });

    it('a page already out of sight takes it as it hears of it', async () => {
      const { heardRelease } = await following();
      hidden = true;
      heardRelease('2');
      expect(reload).toHaveBeenCalledTimes(1);
    });

    it('keeps what the user wrote and did not send', async () => {
      const { heardRelease, takeNewRelease } = await following();
      const message = document.body.appendChild(document.createElement('textarea'));
      const box = document.body.appendChild(document.createElement('input'));
      box.type = 'checkbox';
      box.dispatchEvent(new InputEvent('input', { bubbles: true }));
      typedInto(message, 'pola poruke');
      heardRelease('2');
      away();
      expect(reload).not.toHaveBeenCalled();
      typedInto(message, '');
      takeNewRelease();
      expect(reload).toHaveBeenCalledTimes(1);
    });

    it('waits while something plays', async () => {
      const { heardRelease, takeNewRelease } = await following();
      const video = document.body.appendChild(document.createElement('video'));
      vi.spyOn(video, 'paused', 'get').mockReturnValue(false);
      heardRelease('2');
      away();
      expect(reload).not.toHaveBeenCalled();
      video.remove();
      takeNewRelease();
      expect(reload).toHaveBeenCalledTimes(1);
    });
  });

  it('reloads after a crash only on a page the server has outrun', async () => {
    const { heardRelease, recoverFromCrash } = await fresh();
    heardRelease('1');
    version.mockResolvedValue({ version: '1' });
    recoverFromCrash();
    await vi.waitFor(() => expect(version).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(reload).not.toHaveBeenCalled();
    version.mockResolvedValue({ version: '2' });
    recoverFromCrash();
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  });

  it('asks again while the server is still coming up', async () => {
    vi.useFakeTimers();
    const { heardRelease, recoverFromCrash } = await fresh();
    heardRelease('1');
    version.mockRejectedValueOnce(new TypeError('down'));
    version.mockResolvedValue({ version: '2' });
    recoverFromCrash();
    await vi.advanceTimersByTimeAsync(2_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it('does not guess about a page that never heard a release', async () => {
    const { recoverFromCrash } = await fresh();
    recoverFromCrash();
    expect(version).not.toHaveBeenCalled();
  });
});
