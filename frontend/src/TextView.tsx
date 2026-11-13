import { defaultKeymap } from '@codemirror/commands';
import { HighlightStyle, LanguageDescription, syntaxHighlighting } from '@codemirror/language';
import { languages } from '@codemirror/language-data';
import { highlightSelectionMatches, search, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState } from '@codemirror/state';
import {
  drawSelection,
  EditorView,
  highlightSpecialChars,
  keymap,
  lineNumbers,
} from '@codemirror/view';
import { tags } from '@lezer/highlight';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { getJson } from './api';
import { Loading } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { Failure, nodeKey } from './tree';

interface Shown {
  text: string;
  encoding: string;
  truncated: boolean;
}

const style = HighlightStyle.define([
  {
    tag: [tags.keyword, tags.controlKeyword, tags.operatorKeyword, tags.modifier],
    color: 'var(--code-keyword)',
  },
  { tag: [tags.string, tags.special(tags.string), tags.regexp], color: 'var(--code-string)' },
  { tag: [tags.number, tags.bool, tags.null, tags.atom], color: 'var(--code-number)' },
  { tag: tags.comment, color: 'var(--muted)', fontStyle: 'italic' },
  {
    tag: [
      tags.propertyName,
      tags.attributeName,
      tags.definition(tags.variableName),
      tags.function(tags.variableName),
    ],
    color: 'var(--code-name)',
  },
  { tag: [tags.tagName, tags.typeName, tags.className, tags.meta], color: 'var(--code-meta)' },
  { tag: tags.heading, color: 'var(--code-meta)', fontWeight: 'bold' },
  { tag: tags.strong, fontWeight: 'bold' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.link, color: 'var(--link)', textDecoration: 'underline' },
  { tag: tags.invalid, color: 'var(--danger)' },
]);

const look = EditorView.theme({
  '&': { height: '100%', backgroundColor: 'var(--surface)', color: 'var(--ink)' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { fontFamily: 'var(--font-mono)', fontSize: '13px' },
  '.cm-gutters': {
    backgroundColor: 'var(--panel)',
    color: 'var(--muted)',
    borderRight: '1px solid var(--line)',
  },
  '.cm-cursor': { borderLeftColor: 'var(--accent)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
    backgroundColor: 'var(--selected)',
  },
  '.cm-selectionMatch': { backgroundColor: 'var(--hover)' },
  '.cm-searchMatch': { backgroundColor: 'var(--mark)' },
  '.cm-searchMatch-selected': { backgroundColor: 'var(--comment-active)' },
  '.cm-specialChar': { color: 'var(--danger)' },
  '.cm-panels': { backgroundColor: 'var(--panel)', color: 'var(--ink)' },
  '.cm-panels-top': { borderBottom: '1px solid var(--line)' },
  '.cm-textfield': {
    backgroundColor: 'var(--field)',
    color: 'var(--ink)',
    border: '1px solid var(--line)',
  },
  '.cm-button': {
    backgroundImage: 'none',
    backgroundColor: 'var(--raised)',
    color: 'var(--ink)',
    border: '1px solid var(--line)',
  },
  '.cm-panel button[name=close]': { color: 'var(--muted)' },
});

/** CodeMirror's words a read-only search panel shows, by the key it asks with. */
const PHRASES: Record<string, MessageKey> = {
  Find: 'text.find',
  next: 'text.next',
  previous: 'text.previous',
  all: 'text.all',
  'match case': 'text.matchCase',
  regexp: 'text.regexp',
  'by word': 'text.byWord',
  close: 'text.close',
  'current match': 'text.currentMatch',
  'on line': 'text.onLine',
  'Go to line': 'text.goToLine',
  go: 'text.go',
};

/** A text file read-only, with line numbers, search and highlighting by its name; its first
 * `most` bytes where they are given. */
export default function TextView({
  nodeId,
  name,
  most,
}: {
  nodeId: string;
  name: string;
  most?: number;
}) {
  const { t } = useI18n();
  const shown = useQuery({
    queryKey: [...nodeKey(nodeId), 'text', most],
    queryFn: () =>
      getJson<Shown>(`/api/nodes/${nodeId}/text${most === undefined ? '' : `?most=${most}`}`),
  });
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!shown.data || !host.current) return;
    const language = new Compartment();
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: shown.data.text,
        extensions: [
          lineNumbers(),
          highlightSpecialChars(),
          drawSelection(),
          highlightSelectionMatches(),
          search({ top: true }),
          keymap.of([...searchKeymap, ...defaultKeymap]),
          EditorState.readOnly.of(true),
          EditorState.phrases.of(
            Object.fromEntries(Object.entries(PHRASES).map(([phrase, key]) => [phrase, t(key)])),
          ),
          syntaxHighlighting(style),
          look,
          language.of([]),
        ],
      }),
    });
    let gone = false;
    void LanguageDescription.matchFilename(languages, name)
      ?.load()
      .then((support) => {
        if (!gone) view.dispatch({ effects: language.reconfigure(support) });
      });
    return () => {
      gone = true;
      view.destroy();
    };
  }, [shown.data, name, t]);

  if (shown.isPending) return <Loading />;
  if (shown.isError) return <Failure error={shown.error} />;
  return (
    <div className="flex h-full flex-col">
      <div ref={host} className="min-h-0 flex-1" />
      <p className="flex gap-4 border-t border-line px-3 py-1 text-xs text-muted">
        <span>{shown.data.encoding}</span>
        {shown.data.truncated && <span>{t('text.truncated')}</span>}
      </p>
    </div>
  );
}
