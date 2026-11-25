import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin, type UserConfig } from 'vite';

/** Lightning CSS stands in for light-dark() below its targets with variables that only a literal
 * color-scheme sets, which theme.css's `var(--scheme)` is not: every colour of the interface
 * would come out void, in the build alone. */
export function nativeLightDark(): Plugin {
  return {
    name: 'native-light-dark',
    apply: 'build',
    generateBundle(_, bundle) {
      for (const file of Object.values(bundle)) {
        if (file.type === 'asset' && String(file.source).includes('--lightningcss-')) {
          this.error(`${file.fileName} carries Lightning CSS's light-dark() stand-in`);
        }
      }
    },
  };
}

/** A page a Ponistra OS agent embeds and serves at the root of its own origin under
 * `default-src 'self'` (ponistra-os `agent/API.md`): `<name>/index.html` built into
 * `dist-<name>/`, every asset a file named by its content, nothing inline. */
export function staticPage(name: 'machine' | 'seat'): UserConfig {
  const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));
  return defineConfig({
    root: here(`./${name}`),
    base: '/',
    publicDir: false,
    // Tailwind's own pass targets browsers without light-dark(), so Vite's minifier alone takes
    // the CSS to cssTarget, the browsers that have it.
    plugins: [react(), tailwindcss({ optimize: false }), nativeLightDark()],
    build: {
      outDir: here(`./dist-${name}`),
      emptyOutDir: true,
      cssTarget: ['chrome123', 'edge123', 'firefox120', 'safari17.5', 'ios17.5'],
      assetsInlineLimit: 0,
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: 'react', test: /\/node_modules\/(?:react|react-dom|react-router|scheduler)\// },
              { name: 'hr', test: /\/src\/i18n\/hr\.ts$/ },
              { name: 'en', test: /\/src\/i18n\/en\.ts$/ },
            ],
          },
        },
      },
    },
  });
}
