import { useState } from 'react';
import type * as Y from 'yjs';
import { Cancel, Modal, NumberField, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { primaryButton } from '../styles';
import {
  MARGINS,
  marginsOf,
  ownsPages,
  ownsParts,
  PAPERS,
  paperOf,
  roomForText,
  savePages,
  saveSection,
  sectionOwnsPages,
  setupOf,
  type Margins,
  type PageSetup,
  type Paper,
} from './pages';

const PAPER_NAMES: Record<Paper, string> = {
  a4: 'A4',
  a3: 'A3',
  a5: 'A5',
  b5: 'B5',
  letter: 'Letter',
  legal: 'Legal',
};

const SIDES = ['top', 'bottom', 'left', 'right'] as const;
const OWN = 'own';

/** A section after a break: the break's id, the section's page setup, and the one of the section
 * before, which it takes where it sets none of its own. */
export interface SectionPages {
  id: string;
  setup: PageSetup;
  before: PageSetup;
}

/** The page setup of the section the cursor is in after a break, of the tab, or of the document,
 * which every tab without its own follows. */
export function PageDialog({
  own,
  tab,
  section,
  first,
  several,
  onClose,
}: {
  own: Y.Doc;
  tab: string | null;
  section: SectionPages | null;
  /** Whether the tab is the document's first, which numbers its pages as the document does. */
  first: boolean;
  several: boolean;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const sectioned = tab !== null && section !== null;
  const [owned] = useState(() =>
    sectioned ? sectionOwnsPages(own, tab, section.id) : ownsPages(own, tab),
  );
  const [mine, setMine] = useState(owned);
  const [draft, setDraft] = useState(() => (sectioned ? section.setup : setupOf(own, tab)));
  const change = (patch: Partial<PageSetup>) => setDraft((setup) => ({ ...setup, ...patch }));
  const landscape = draft.width > draft.height;
  const paper = paperOf(draft);
  const margins = marginsOf(draft);
  const numbered = mine || (first && !sectioned);
  const fits = roomForText(draft);

  const choose = (next: boolean) => {
    setMine(next);
    if (!next) setDraft(sectioned ? section.before : setupOf(own, null));
    else if (owned) setDraft(sectioned ? section.setup : setupOf(own, tab));
  };
  const turn = (wide: boolean) => {
    if (wide !== landscape) change({ width: draft.height, height: draft.width });
  };
  const size = ([short, long]: readonly [number, number]) =>
    `${formatNumber(short)} × ${formatNumber(long)} cm`;
  const sides = ({ top, left }: (typeof MARGINS)[Margins]) =>
    top === left ? `${formatNumber(top)} cm` : `${formatNumber(top)} / ${formatNumber(left)} cm`;
  const apply = () => {
    if (sectioned) saveSection(own, tab, section.id, mine ? draft : null);
    else savePages(own, tab, draft, mine);
    onClose();
  };

  return (
    <Modal heading={t('page.title')} onClose={onClose}>
      {sectioned && (
        <Picker
          label={t('page.sectionSource')}
          value={mine ? OWN : 'before'}
          options={[
            ['before', t('page.fromSection')],
            [OWN, t('page.own')],
          ]}
          onChange={(value) => choose(value === OWN)}
        />
      )}
      {tab && !sectioned && (several || owned) && (
        <div className="flex flex-col gap-1">
          <Picker
            label={t('page.source')}
            value={mine ? OWN : 'document'}
            options={[
              ['document', t('page.fromDocument')],
              [OWN, t('page.own')],
            ]}
            onChange={(value) => choose(value === OWN)}
          />
          {!mine && owned && ownsParts(own, tab) && (
            <p className="text-sm text-danger">{t('page.dropsParts')}</p>
          )}
          {!mine && several && <p className="text-sm text-muted">{t('page.forAll')}</p>}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Picker
          label={t('page.paper')}
          value={paper ?? OWN}
          options={[
            ...Object.entries(PAPERS).map(
              ([name, dimensions]) =>
                [name, `${PAPER_NAMES[name as Paper]} (${size(dimensions)})`] as const,
            ),
            [OWN, t('page.ownSize')] as const,
          ]}
          onChange={(name) => {
            if (name === OWN) return;
            const [short, long] = PAPERS[name as Paper];
            change(landscape ? { width: long, height: short } : { width: short, height: long });
          }}
        />
        <Picker
          label={t('page.orientation')}
          value={landscape ? 'landscape' : 'portrait'}
          options={[
            ['portrait', t('page.portrait')],
            ['landscape', t('page.landscape')],
          ]}
          onChange={(value) => turn(value === 'landscape')}
        />
        <NumberField
          label={t('page.width')}
          value={draft.width}
          min={5}
          max={60}
          step={0.1}
          onChange={(width) => change({ width })}
        />
        <NumberField
          label={t('page.height')}
          value={draft.height}
          min={5}
          max={60}
          step={0.1}
          onChange={(height) => change({ height })}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="col-span-full">
          <Picker
            label={t('page.margins')}
            value={margins ?? OWN}
            options={[
              ...Object.entries(MARGINS).map(
                ([name, preset]) =>
                  [name, `${t(`page.margins.${name}` as MessageKey)} (${sides(preset)})`] as const,
              ),
              [OWN, t('page.margins.own')] as const,
            ]}
            onChange={(name) => name !== OWN && change(MARGINS[name as Margins])}
          />
        </div>
        {SIDES.map((side) => (
          <NumberField
            key={side}
            label={t(`page.${side}`)}
            value={draft[side]}
            min={0}
            max={30}
            step={0.1}
            onChange={(length) => change({ [side]: length })}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          label={t('page.header')}
          value={draft.header}
          min={0}
          max={15}
          step={0.1}
          onChange={(header) => change({ header })}
        />
        <NumberField
          label={t('page.footer')}
          value={draft.footer}
          min={0}
          max={15}
          step={0.1}
          onChange={(footer) => change({ footer })}
        />
        <label className="col-span-full flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.firstPage}
            onChange={(event) => change({ firstPage: event.target.checked })}
          />
          {t('page.firstPage')}
        </label>
      </div>
      <div className="grid grid-cols-2 items-end gap-3">
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            disabled={!numbered}
            checked={numbered && draft.start !== null}
            onChange={(event) => change({ start: event.target.checked ? 1 : null })}
          />
          {t('page.restart')}
        </label>
        <NumberField
          label={t('page.start')}
          value={draft.start ?? 1}
          min={0}
          max={9999}
          step={1}
          disabled={!numbered || draft.start === null}
          onChange={(start) => change({ start: Math.round(start) })}
        />
        {!numbered && <p className="col-span-full text-sm text-muted">{t('page.continues')}</p>}
      </div>
      {!fits && <p className="text-sm text-danger">{t('page.noRoom')}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <Cancel />
        <button type="button" disabled={!fits} onClick={apply} className={primaryButton}>
          {t('page.apply')}
        </button>
      </div>
    </Modal>
  );
}
