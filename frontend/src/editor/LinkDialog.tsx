import { ExternalLink, Pencil, Unlink } from 'lucide-react';
import type { EditorState } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import { useState, type FormEvent, type RefObject } from 'react';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { ResultSummary, resultHref, SHORTEST, useSearch } from '../search';
import { field, iconButton, primaryButton } from '../styles';
import { selectedImage } from './images';
import { linkAt, removeLink, setLink } from './links';
import { safeHref } from './schema';

const FOUND = 5;

export function LinkDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t } = useI18n();
  const [initial] = useState(() => {
    const found = linkAt(view.state);
    const { from, to } = found ?? view.state.selection;
    return { text: view.state.doc.textBetween(from, to), href: found?.href ?? '' };
  });
  const [text, setText] = useState(initial.text);
  const [href, setHref] = useState(initial.href);
  const [query, setQuery] = useState('');
  const [invalid, setInvalid] = useState(false);
  const search = useSearch(query, { kind: 'document' }, FOUND);
  const results = query.trim().length >= SHORTEST ? (search.data?.documents ?? []) : [];

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!safeHref(href)) {
      setInvalid(true);
      return;
    }
    setLink(text || href, href)(view.state, view.dispatch);
    onClose();
  }

  return (
    <Modal heading={t('command.link')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('link.text')}
          <input value={text} onChange={(event) => setText(event.target.value)} className={field} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('link.href')}
          <input
            autoFocus
            required
            value={href}
            aria-invalid={invalid}
            onChange={(event) => {
              setHref(event.target.value);
              setInvalid(false);
            }}
            placeholder="https://"
            className={field}
          />
        </label>
        {invalid && <p className="text-sm text-danger">{t('link.invalid')}</p>}
        <label className="flex flex-col gap-1 text-sm">
          {t('link.find')}
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className={field}
          />
        </label>
        {results.length > 0 && (
          <ul className="-mt-2 flex flex-col">
            {results.map((result) => (
              <li key={result.id}>
                <button
                  type="button"
                  onClick={() => {
                    setHref(resultHref(result));
                    setInvalid(false);
                    if (!text) setText(result.title);
                  }}
                  className="flex w-full rounded px-2 py-1.5 text-left hover:bg-hover"
                >
                  <ResultSummary result={result} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** What the link under the cursor leads to, and what can be done with it. */
export function LinkPopover({
  view,
  state,
  around,
  onFollow,
  onEdit,
}: {
  view: EditorView;
  state: EditorState;
  around: RefObject<HTMLElement | null>;
  onFollow: (href: string) => void;
  onEdit: () => void;
}) {
  const { t } = useI18n();
  const found = linkAt(state);
  if (!found || !around.current) return null;
  const at = view.coordsAtPos(found.from);
  const box = around.current.getBoundingClientRect();
  const keep = (event: { preventDefault: () => void }) => event.preventDefault();
  return (
    <div
      role="toolbar"
      aria-label={t('command.link')}
      onMouseDown={keep}
      style={{ left: Math.max(0, at.left - box.left), top: at.bottom - box.top + 4 }}
      className="absolute z-20 flex max-w-[min(28rem,100%)] items-center gap-1 rounded border border-line bg-raised p-1 text-sm shadow-lg"
    >
      <a
        href={found.href}
        onClick={(event) => {
          event.preventDefault();
          onFollow(found.href);
        }}
        className="min-w-0 truncate px-1 underline"
      >
        {found.href}
      </a>
      <button
        type="button"
        title={t('link.open')}
        aria-label={t('link.open')}
        onClick={() => onFollow(found.href)}
        className={iconButton}
      >
        <ExternalLink size={16} aria-hidden />
      </button>
      <button
        type="button"
        title={t('link.edit')}
        aria-label={t('link.edit')}
        onClick={onEdit}
        className={iconButton}
      >
        <Pencil size={16} aria-hidden />
      </button>
      <button
        type="button"
        title={t('link.remove')}
        aria-label={t('link.remove')}
        onClick={() => removeLink(view.state, view.dispatch)}
        className={iconButton}
      >
        <Unlink size={16} aria-hidden />
      </button>
    </div>
  );
}

export function AltDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t } = useI18n();
  const [picked] = useState(() => selectedImage(view.state));
  const [alt, setAlt] = useState(() => String(picked?.node.attrs.alt ?? ''));

  function submit(event: FormEvent) {
    event.preventDefault();
    const now = selectedImage(view.state) ?? picked;
    if (now && view.state.doc.nodeAt(now.pos)?.attrs.id === picked?.node.attrs.id) {
      view.dispatch(view.state.tr.setNodeAttribute(now.pos, 'alt', alt.trim()));
    }
    onClose();
  }

  return (
    <Modal heading={t('command.imageAlt')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('imageAlt.hint')}
          <textarea
            autoFocus
            rows={3}
            maxLength={500}
            value={alt}
            onChange={(event) => setAlt(event.target.value)}
            className={field}
          />
        </label>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
