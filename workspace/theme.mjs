// PONISTRA's interface colours as two VS Code colour themes, light and dark, read from theme.css,
// the one source of them: node theme.mjs <theme.css> <extension directory>
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [source, out] = process.argv.slice(2);
const css = readFileSync(source, 'utf8');
const root = css.slice(css.indexOf(':root {'), css.indexOf('\n}', css.indexOf(':root {')));
const declared = Object.fromEntries(
  [...root.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]),
);

function split(value) {
  let depth = 0;
  for (let i = 0; i < value.length; i++) {
    if (value[i] === '(') depth++;
    else if (value[i] === ')') depth--;
    else if (value[i] === ',' && depth === 0) return [value.slice(0, i).trim(), value.slice(i + 1).trim()];
  }
  throw new Error(`light-dark() without two values: ${value}`);
}

function resolve(name, scheme) {
  const value = declared[name];
  if (value === undefined) throw new Error(`theme.css has no --${name}`);
  const pair = value.match(/^light-dark\((.*)\)$/s);
  const chosen = pair ? split(pair[1])[scheme === 'light' ? 0 : 1] : value;
  const reference = chosen.match(/^var\(--([\w-]+)\)$/);
  if (reference) return resolve(reference[1], scheme);
  if (!/^#[0-9a-f]{6}$/i.test(chosen)) throw new Error(`--${name} is not a hex colour: ${chosen}`);
  return chosen;
}

const colors = {
  foreground: 'ink',
  descriptionForeground: 'muted',
  disabledForeground: 'control',
  errorForeground: 'danger',
  focusBorder: 'focus',
  'icon.foreground': 'control',
  'textLink.foreground': 'link',
  'textLink.activeForeground': 'accent-hover',
  'selection.background': 'selected',
  'widget.border': 'line',
  'sash.hoverBorder': 'focus',
  'editor.background': 'surface',
  'editor.foreground': 'ink',
  'editor.lineHighlightBackground': 'hover',
  'editor.selectionBackground': 'selected',
  'editor.inactiveSelectionBackground': 'hover',
  'editor.findMatchHighlightBackground': 'mark',
  'editorLineNumber.foreground': 'control',
  'editorLineNumber.activeForeground': 'ink',
  'editorCursor.foreground': 'accent',
  'editorWidget.background': 'raised',
  'editorWidget.border': 'line',
  'editorHoverWidget.background': 'raised',
  'editorHoverWidget.border': 'line',
  'editorSuggestWidget.background': 'raised',
  'editorSuggestWidget.border': 'line',
  'editorSuggestWidget.selectedBackground': 'selected',
  'editorError.foreground': 'danger',
  'editorGroup.border': 'line',
  'editorGroupHeader.tabsBackground': 'panel',
  'tab.activeBackground': 'surface',
  'tab.activeForeground': 'ink',
  'tab.inactiveBackground': 'panel',
  'tab.inactiveForeground': 'muted',
  'tab.border': 'line',
  'tab.activeBorderTop': 'accent',
  'activityBar.background': 'panel',
  'activityBar.foreground': 'ink',
  'activityBar.inactiveForeground': 'control',
  'activityBar.border': 'line',
  'activityBar.activeBorder': 'accent',
  'activityBarBadge.background': 'accent',
  'activityBarBadge.foreground': 'on-accent',
  'sideBar.background': 'panel',
  'sideBar.foreground': 'ink',
  'sideBar.border': 'line',
  'sideBarSectionHeader.background': 'panel',
  'sideBarSectionHeader.foreground': 'ink',
  'sideBarTitle.foreground': 'ink',
  'titleBar.activeBackground': 'panel',
  'titleBar.activeForeground': 'ink',
  'titleBar.inactiveBackground': 'panel',
  'titleBar.inactiveForeground': 'muted',
  'titleBar.border': 'line',
  'statusBar.background': 'panel',
  'statusBar.foreground': 'muted',
  'statusBar.border': 'line',
  'statusBar.noFolderBackground': 'panel',
  'statusBarItem.remoteBackground': 'accent',
  'statusBarItem.remoteForeground': 'on-accent',
  'panel.background': 'surface',
  'panel.border': 'line',
  'panelTitle.activeForeground': 'ink',
  'panelTitle.inactiveForeground': 'muted',
  'panelTitle.activeBorder': 'accent',
  'terminal.background': 'surface',
  'terminal.foreground': 'ink',
  'terminalCursor.foreground': 'accent',
  'input.background': 'field',
  'input.foreground': 'ink',
  'input.border': 'line',
  'input.placeholderForeground': 'control',
  'inputOption.activeBorder': 'focus',
  'dropdown.background': 'raised',
  'dropdown.foreground': 'ink',
  'dropdown.border': 'line',
  'checkbox.background': 'field',
  'checkbox.border': 'line',
  'button.background': 'accent',
  'button.foreground': 'on-accent',
  'button.hoverBackground': 'accent-hover',
  'button.secondaryBackground': 'hover',
  'button.secondaryForeground': 'ink',
  'badge.background': 'accent',
  'badge.foreground': 'on-accent',
  'list.hoverBackground': 'hover',
  'list.activeSelectionBackground': 'selected',
  'list.activeSelectionForeground': 'ink',
  'list.inactiveSelectionBackground': 'selected',
  'list.inactiveSelectionForeground': 'ink',
  'list.focusOutline': 'focus',
  'list.highlightForeground': 'accent',
  'list.errorForeground': 'danger',
  'menu.background': 'raised',
  'menu.foreground': 'ink',
  'menu.selectionBackground': 'selected',
  'menu.selectionForeground': 'ink',
  'menu.border': 'line',
  'menu.separatorBackground': 'line',
  'quickInput.background': 'raised',
  'quickInput.foreground': 'ink',
  'quickInputList.focusBackground': 'selected',
  'quickInputList.focusForeground': 'ink',
  'notifications.background': 'raised',
  'notifications.foreground': 'ink',
  'notifications.border': 'line',
  'progressBar.background': 'accent',
  'gitDecoration.addedResourceForeground': 'inserted',
  'gitDecoration.untrackedResourceForeground': 'inserted',
  'gitDecoration.deletedResourceForeground': 'deleted',
  'gitDecoration.modifiedResourceForeground': 'code-number',
  'gitDecoration.ignoredResourceForeground': 'control',
  'gitDecoration.conflictingResourceForeground': 'danger',
};

// Translucent over the text, so the changed words still read through them.
const tinted = {
  'diffEditor.insertedTextBackground': ['inserted', '33'],
  'diffEditor.removedTextBackground': ['deleted', '33'],
  'scrollbarSlider.background': ['control', '40'],
  'scrollbarSlider.hoverBackground': ['control', '66'],
  'scrollbarSlider.activeBackground': ['control', '88'],
};

const tokens = [
  ['comment', 'muted', 'italic'],
  ['keyword, storage, storage.type, keyword.operator.new, keyword.control', 'code-keyword'],
  ['string, string.template, markup.inline.raw', 'code-string'],
  ['constant.numeric, constant.language, constant.character, support.constant', 'code-number'],
  ['entity.name, entity.name.function, entity.name.type, support.function, support.type, support.class', 'code-name'],
  ['meta.decorator, entity.name.tag, entity.other.attribute-name, meta.preprocessor', 'code-meta'],
  ['invalid', 'danger'],
  ['markup.heading', 'accent', 'bold'],
  ['markup.inserted', 'inserted'],
  ['markup.deleted', 'deleted'],
];

function theme(scheme) {
  return {
    name: `Ponistra ${scheme === 'light' ? 'Light' : 'Dark'}`,
    type: scheme,
    colors: {
      ...Object.fromEntries(Object.entries(colors).map(([key, token]) => [key, resolve(token, scheme)])),
      ...Object.fromEntries(Object.entries(tinted).map(([key, [token, alpha]]) => [key, resolve(token, scheme) + alpha])),
    },
    tokenColors: tokens.map(([scope, token, fontStyle]) => ({
      scope: scope.split(', '),
      settings: { foreground: resolve(token, scheme), ...(fontStyle && { fontStyle }) },
    })),
  };
}

mkdirSync(join(out, 'themes'), { recursive: true });
writeFileSync(
  join(out, 'package.json'),
  JSON.stringify(
    {
      name: 'ponistra-theme',
      displayName: 'Ponistra',
      publisher: 'ponistra',
      version: '1.0.0',
      engines: { vscode: '*' },
      categories: ['Themes'],
      contributes: {
        themes: [
          { label: 'Ponistra Light', uiTheme: 'vs', path: './themes/light.json' },
          { label: 'Ponistra Dark', uiTheme: 'vs-dark', path: './themes/dark.json' },
        ],
      },
    },
    null,
    2,
  ),
);
for (const scheme of ['light', 'dark']) {
  writeFileSync(join(out, 'themes', `${scheme}.json`), JSON.stringify(theme(scheme), null, 2));
}
