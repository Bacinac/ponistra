// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';
import { BESIDE, useGoToProjects } from './workspace';

const navigate = vi.fn();
vi.mock('react-router', async (actual) => ({
  ...(await actual<typeof import('react-router')>()),
  useNavigate: () => navigate,
}));

function pointer(fine: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: fine, media: query }));
}

function going(): () => void {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>{children}</MemoryRouter>
  );
  return renderHook(() => useGoToProjects(), { wrapper }).result.current;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  navigate.mockClear();
});

test('on a computer Projects open in their own window beside the app, as a meeting does', () => {
  pointer(true);
  const beside = { location: { pathname: '/', href: '/' }, focus: vi.fn() };
  const opened = vi.spyOn(window, 'open').mockReturnValue(beside as unknown as Window);
  going()();
  expect(opened).toHaveBeenCalledWith('', 'ponistra-projects', expect.stringMatching(/^popup,/));
  expect(beside.location.href).toBe(BESIDE);
  expect(beside.focus).toHaveBeenCalledOnce();
  expect(navigate).not.toHaveBeenCalled();
});

test('where the browser keeps the window from opening, Projects open here saying so', () => {
  pointer(true);
  vi.spyOn(window, 'open').mockReturnValue(null);
  going()();
  expect(navigate).toHaveBeenCalledWith('/workspace', { state: { blocked: true } });
});

test('on a phone Projects open here', () => {
  pointer(false);
  const opened = vi.spyOn(window, 'open');
  going()();
  expect(opened).not.toHaveBeenCalled();
  expect(navigate).toHaveBeenCalledWith('/workspace');
});
