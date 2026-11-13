// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { hear, reachable } from './live';

class FakeSocket extends EventTarget {
  static made: FakeSocket[] = [];
  readyState = 0;

  constructor(readonly url: string) {
    super();
    FakeSocket.made.push(this);
  }

  close(): void {
    this.readyState = 3;
  }

  opened(): void {
    this.readyState = 1;
    this.dispatchEvent(new Event('open'));
  }

  closed(code: number): void {
    this.readyState = 3;
    this.dispatchEvent(new CloseEvent('close', { code }));
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', FakeSocket);
  FakeSocket.made = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it('counts a socket refused, as nobody signed in, as the server reached, and a lost one as not', () => {
  const leave = hear(() => {});
  FakeSocket.made.at(-1)!.closed(4403);
  expect(reachable()).toBe(true);
  vi.advanceTimersByTime(500);
  const again = FakeSocket.made.at(-1)!;
  again.opened();
  again.closed(1006);
  expect(reachable()).toBe(false);
  vi.advanceTimersByTime(500);
  FakeSocket.made.at(-1)!.opened();
  expect(reachable()).toBe(true);
  leave();
});
