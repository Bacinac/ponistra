import { useMutation } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { createElement, useId, useMemo, useState } from 'react';
import * as Y from 'yjs';
import { getBytes } from '../api';
import { Cancel, Labelled, Modal, NumberField, Picker } from '../dialogs';
import { FAMILIES, FONT_NAMES, THEMES } from '../fonts';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { SHORTEST, useSearch } from '../search';
import { button, field, primaryButton } from '../styles';
import { errorMessage, KindIcon } from '../tree';
import { shortId } from './blocks';
import { inPalette, TEXT_COLORS, type TextColor } from './colors';
import { numbered } from './numbering';
import { numeral } from './numerals';
import { ALIGNMENTS, LEVELS, schema, type Alignment } from './schema';
import {
  blockOf,
  KIND_LABELS,
  KINDS,
  NUMBERINGS,
  ownStyles,
  saveStyling,
  stylesheet,
  stylingOf,
  type Kind,
  type Style,
  type Styling,
} from './styling';

const ALIGN_LABELS: Record<Alignment, MessageKey> = {
  left: 'command.alignLeft',
  center: 'command.alignCenter',
  right: 'command.alignRight',
  justify: 'command.alignJustify',
};

const DOCUMENTS = { kind: 'document' } as const;

const HEADINGS = LEVELS.map((level) => `h${level}` as const);

/** The number the style shows on its first block, below the first heading of each level above. */
function sampleNumber(styling: Styling, id: string): string | null {
  const { kind } = styling.styles[id];
  const { type, attrs } = blockOf(kind);
  const above = LEVELS.filter((level) => kind.startsWith('h') && level < attrs.level);
  const doc = schema.nodes.doc.create(null, [
    ...above.map((level) => schema.nodes.heading.create({ level })),
    type.create({ ...attrs, style: id === kind ? null : id }),
  ]);
  const at = doc.content.size - doc.lastChild!.nodeSize;
  return numbered(doc, styling, {}, () => null).labels.get(at) ?? null;
}

function headingsNumbered(styling: Styling): boolean {
  return HEADINGS.every((kind) => styling.styles[kind]?.numbering);
}

/** Every heading numbered as 1., 1.1., 1.1.1., or none of them. */
function numberHeadings(styling: Styling, on: boolean): Styling {
  const styles = { ...styling.styles };
  for (const kind of HEADINGS) {
    if (!styles[kind]) continue;
    styles[kind] = on
      ? {
          ...styles[kind],
          numbering: '1',
          prefix: '',
          suffix: '.',
          nested: kind !== 'h1',
        }
      : { ...styles[kind], numbering: '' };
  }
  return { ...styling, styles };
}

function familyLabel(name: string): string {
  const family = FAMILIES.find((found) => found.name === name)!;
  const also = [
    ...(family.replaces ?? []),
    ...(family.resembles ?? []).map((other) => `≈ ${other}`),
  ];
  return also.length ? `${name} (${also.join(', ')})` : name;
}

function Preview({ styling, id }: { styling: Styling; id: string }) {
  const { t } = useI18n();
  const scope = useId();
  const sheet = useMemo(() => stylesheet(scope, styling), [scope, styling]);
  const { kind } = styling.styles[id];
  const own = id === kind ? undefined : id;
  const block = (name: Kind, text: string, style?: string, number?: string | null) => {
    const tag = name === 'text' || name === 'title' || name === 'subtitle' ? 'p' : name;
    const marked = name === 'title' || name === 'subtitle' ? name : undefined;
    return createElement(
      tag,
      {
        'data-block': marked,
        'data-style': style,
        'data-number': number ?? undefined,
      },
      text,
    );
  };
  return (
    <figure className="flex flex-col gap-1 text-sm">
      <figcaption className="text-muted">{t('styles.preview')}</figcaption>
      <style>{sheet}</style>
      <div data-styling={scope} className="max-h-56 overflow-hidden rounded border border-line p-4">
        <div className="ProseMirror">
          {block(kind, t('styles.sample'), own, sampleNumber(styling, id))}
          {block('text', t('styles.sampleText'))}
        </div>
      </div>
    </figure>
  );
}

function StyleFields({
  id,
  styling,
  onChange,
}: {
  id: string;
  styling: Styling;
  onChange: (patch: Partial<Style>) => void;
}) {
  const { t } = useI18n();
  const style = styling.styles[id];
  const own = id !== style.kind;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {own ? (
        <>
          <Labelled label={t('styles.name')}>
            {(id) => (
              <input
                id={id}
                value={style.name}
                maxLength={80}
                onChange={(event) => onChange({ name: event.target.value })}
                className={field}
              />
            )}
          </Labelled>
          <Picker
            label={t('styles.kind')}
            value={style.kind}
            options={KINDS.map((kind) => [kind, t(KIND_LABELS[kind])] as const)}
            onChange={(kind) => onChange({ kind })}
          />
        </>
      ) : (
        <p className="col-span-full font-semibold">{t(KIND_LABELS[style.kind])}</p>
      )}
      <Picker
        label={t('styles.font')}
        value={style.font}
        options={[
          ['headings', `${t('styles.headingsFont')}: ${styling.theme.headings}`],
          ['text', `${t('styles.textFont')}: ${styling.theme.text}`],
          ...FONT_NAMES.map((name) => [name, familyLabel(name)] as const),
        ]}
        onChange={(font) => onChange({ font })}
      />
      <NumberField
        label={t('styles.size')}
        value={style.size}
        min={1}
        max={400}
        step={0.5}
        onChange={(size) => onChange({ size })}
      />
      <div className="flex items-end gap-4 pb-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={style.bold}
            onChange={(event) => onChange({ bold: event.target.checked })}
          />
          {t('command.bold')}
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={style.italic}
            onChange={(event) => onChange({ italic: event.target.checked })}
          />
          {t('command.italic')}
        </label>
      </div>
      <Picker
        label={t('command.color')}
        value={style.color ?? ''}
        options={[
          ['', t('styles.automatic')],
          ...(Object.keys(TEXT_COLORS) as TextColor[]).map(
            (name) => [name, t(`color.${name}` as MessageKey)] as const,
          ),
          ...(style.color && !inPalette(TEXT_COLORS, style.color)
            ? [[style.color, t('styles.original')] as const]
            : []),
        ]}
        onChange={(color) => onChange({ color: color || null })}
      />
      <Picker
        label={t('editor.align')}
        value={style.align ?? 'left'}
        options={ALIGNMENTS.map((align) => [align, t(ALIGN_LABELS[align])] as const)}
        onChange={(align) => onChange({ align: align === 'left' ? null : align })}
      />
      <NumberField
        label={t('styles.before')}
        value={style.before}
        min={0}
        max={400}
        step={1}
        onChange={(before) => onChange({ before })}
      />
      <NumberField
        label={t('styles.after')}
        value={style.after}
        min={0}
        max={400}
        step={1}
        onChange={(after) => onChange({ after })}
      />
      <NumberField
        label={t('styles.line')}
        value={style.line}
        min={0.5}
        max={5}
        step={0.05}
        onChange={(line) => onChange({ line })}
      />
      <Picker
        label={t('styles.numbering')}
        value={style.numbering}
        options={NUMBERINGS.map(
          (numbering) =>
            [
              numbering,
              numbering
                ? [1, 2, 3].map((count) => numeral(count, numbering)).join(', ')
                : t('styles.numberingNone'),
            ] as const,
        )}
        onChange={(numbering) => onChange({ numbering })}
      />
      {style.numbering && (
        <>
          {(['prefix', 'suffix'] as const).map((affix) => (
            <Labelled key={affix} label={t(`styles.${affix}`)}>
              {(id) => (
                <input
                  id={id}
                  value={style[affix]}
                  maxLength={40}
                  onChange={(event) => onChange({ [affix]: event.target.value })}
                  className={field}
                />
              )}
            </Labelled>
          ))}
          {style.kind !== 'h1' && style.kind.startsWith('h') && (
            <label className="col-span-full flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={style.nested}
                onChange={(event) => onChange({ nested: event.target.checked })}
              />
              {t('styles.nested')}
            </label>
          )}
        </>
      )}
    </div>
  );
}

function FromDocument({
  documentId,
  onTaken,
}: {
  documentId: string;
  onTaken: (styling: Styling, title: string) => void;
}) {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const found = useSearch(query, DOCUMENTS, 8);
  const take = useMutation({
    mutationFn: async ({ id }: { id: string; title: string }) => {
      const doc = new Y.Doc();
      Y.applyUpdate(doc, await getBytes(`/api/nodes/${id}/state`));
      const styling = stylingOf(doc);
      doc.destroy();
      return styling;
    },
    onSuccess: (styling, { title }) => onTaken(styling, title),
  });
  const others = [
    ...new Map(
      (found.data?.documents ?? [])
        .filter((result) => result.id !== documentId)
        .map((result) => [result.id, result]),
    ).values(),
  ];
  const searched = query.trim().length >= SHORTEST && found.isSuccess;
  return (
    <div className="flex flex-col gap-2 rounded border border-line p-3">
      <input
        type="search"
        autoFocus
        aria-label={t('styles.from')}
        placeholder={t('styles.fromHint')}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className={field}
      />
      {others.length > 0 && (
        <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded border border-line">
          {others.map((result) => (
            <li key={result.id}>
              <button
                type="button"
                disabled={take.isPending}
                onClick={() => take.mutate({ id: result.id, title: result.title })}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-hover"
              >
                <KindIcon kind="document" decorative />
                <span className="truncate">{result.title}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {searched && others.length === 0 && (
        <p className="text-sm text-muted">{t('styles.fromNone')}</p>
      )}
      {(found.error ?? take.error) && (
        <p className="text-sm text-danger">{errorMessage((found.error ?? take.error)!, t)}</p>
      )}
    </div>
  );
}

/** The document's theme and styles, changed together and written on Apply. */
export function StylesDialog({
  doc,
  documentId,
  onClose,
}: {
  doc: Y.Doc;
  documentId: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [original] = useState(() => stylingOf(doc));
  const [draft, setDraft] = useState(original);
  const [selected, setSelected] = useState('text');
  const [choosing, setChoosing] = useState(false);
  const [taken, setTaken] = useState<string | null>(null);
  const preset = THEMES.find(
    ({ theme }) => theme.headings === draft.theme.headings && theme.text === draft.theme.text,
  );
  const builtIn = KINDS.filter((kind) => draft.styles[kind]).map(
    (kind) => [kind, t(KIND_LABELS[kind])] as const,
  );
  const own = ownStyles(draft).map(([id, style]) => [id, style.name] as const);
  const shown = draft.styles[selected] ? selected : 'text';
  const unnamed = own.some(([, name]) => !name.trim());

  const change = (patch: Partial<Style>) =>
    setDraft((styling) => ({
      ...styling,
      styles: {
        ...styling.styles,
        [shown]: { ...styling.styles[shown], ...patch },
      },
    }));
  const add = () => {
    const id = shortId();
    setDraft((styling) => ({
      ...styling,
      styles: {
        ...styling.styles,
        [id]: { ...styling.styles[shown], name: t('styles.newName') },
      },
    }));
    setSelected(id);
  };
  const remove = () => {
    setDraft((styling) => {
      const { [shown]: _removed, ...styles } = styling.styles;
      return { ...styling, styles };
    });
    setSelected('text');
  };
  const apply = () => {
    const styles = Object.fromEntries(
      Object.entries(draft.styles).map(([id, style]) => [
        id,
        { ...style, name: style.name.trim() },
      ]),
    );
    saveStyling(doc, original, { ...draft, styles });
    onClose();
  };

  const entry = ([id, label]: readonly [string, string]) => (
    <li key={id}>
      <button
        type="button"
        aria-pressed={id === shown}
        onClick={() => setSelected(id)}
        className="w-full truncate rounded px-2 py-1.5 text-left text-sm hover:bg-hover aria-pressed:bg-selected aria-pressed:font-semibold"
      >
        {label || t('styles.unnamed')}
      </button>
    </li>
  );

  return (
    <Modal heading={t('styles.title')} wide onClose={onClose}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Picker
          label={t('styles.theme')}
          value={preset?.id ?? ''}
          options={[
            ...(preset ? [] : [['', t('styles.ownTheme')] as const]),
            ...THEMES.map(({ id }) => [id, t(`theme.${id}` as MessageKey)] as const),
          ]}
          onChange={(id) => {
            const chosen = THEMES.find((found) => found.id === id);
            if (chosen) setDraft((styling) => ({ ...styling, theme: chosen.theme }));
          }}
        />
        {(['headings', 'text'] as const).map((role) => (
          <Picker
            key={role}
            label={t(role === 'headings' ? 'styles.headingsFont' : 'styles.textFont')}
            value={draft.theme[role]}
            options={FONT_NAMES.map((name) => [name, familyLabel(name)] as const)}
            onChange={(name) =>
              setDraft((styling) => ({
                ...styling,
                theme: { ...styling.theme, [role]: name },
              }))
            }
          />
        ))}
        <label className="col-span-full flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={headingsNumbered(draft)}
            onChange={(event) =>
              setDraft((styling) => numberHeadings(styling, event.target.checked))
            }
          />
          {t('styles.numberHeadings')}
        </label>
      </div>
      {choosing && (
        <FromDocument
          documentId={documentId}
          onTaken={(styling, title) => {
            setDraft(styling);
            setSelected('text');
            setChoosing(false);
            setTaken(title);
          }}
        />
      )}
      {taken && (
        <p className="text-sm text-muted">
          {t('styles.taken')}: <strong className="text-ink">{taken}</strong>
        </p>
      )}
      <div className="flex flex-col gap-4 sm:flex-row">
        <nav aria-label={t('styles.list')} className="flex shrink-0 flex-col gap-2 sm:w-44">
          <ul className="flex flex-col gap-0.5">{builtIn.map(entry)}</ul>
          {own.length > 0 && (
            <ul className="flex flex-col gap-0.5 border-t border-line pt-2">{own.map(entry)}</ul>
          )}
          <div className="flex gap-1">
            <button type="button" onClick={add} className={button}>
              <Plus size={16} aria-hidden />
              {t('styles.new')}
            </button>
            <button
              type="button"
              aria-label={t('styles.delete')}
              title={t('styles.delete')}
              disabled={shown === draft.styles[shown].kind}
              onClick={remove}
              className={button}
            >
              <Trash2 size={16} aria-hidden />
            </button>
          </div>
        </nav>
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <StyleFields key={shown} id={shown} styling={draft} onChange={change} />
          <Preview styling={draft} id={shown} />
        </div>
      </div>
      {unnamed && <p className="text-sm text-danger">{t('styles.nameNeeded')}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-pressed={choosing}
          onClick={() => setChoosing(!choosing)}
          className={`${button} aria-pressed:bg-selected`}
        >
          {t('styles.from')}
        </button>
        <span className="ml-auto" />
        <Cancel />
        <button type="button" disabled={unnamed} onClick={apply} className={primaryButton}>
          {t('styles.apply')}
        </button>
      </div>
    </Modal>
  );
}
