// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { choosePageTheme, chooseTheme, isDark, useThemeOf } from './theme';

afterEach(() => {
  chooseTheme('system');
  choosePageTheme('projects', 'ponistra');
  choosePageTheme('meetings', 'ponistra');
});

test("a page's own theme holds only while the page is shown, and Ponistra's again after it", () => {
  chooseTheme('light');
  choosePageTheme('projects', 'dark');
  const root = document.documentElement;
  expect(root.dataset.theme).toBe('light');
  const { unmount } = renderHook(() => useThemeOf('projects'));
  expect(root.dataset.theme).toBe('dark');
  expect(isDark()).toBe(true);
  choosePageTheme('projects', 'ponistra');
  expect(root.dataset.theme).toBe('light');
  choosePageTheme('projects', 'dark');
  unmount();
  expect(root.dataset.theme).toBe('light');
  expect(isDark()).toBe(false);
});

test("a page with Ponistra's theme follows Ponistra's, the system's included", () => {
  chooseTheme('system');
  choosePageTheme('meetings', 'light');
  const { unmount } = renderHook(() => useThemeOf('projects'));
  expect(document.documentElement.dataset.theme).toBeUndefined();
  unmount();
});
