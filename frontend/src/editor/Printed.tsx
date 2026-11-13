import type { EditorView } from 'prosemirror-view';
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { yXmlFragmentToProseMirrorRootNode } from 'y-prosemirror';
import * as Y from 'yjs';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import type { DocumentLocale, Tab } from '../tree';
import { chaptersOf, contentsStore } from './contents';
import { savedView, useStylesheet } from './Editor';
import { writtenDate } from './formats';
import { formatsOf, savedLists, type ListStore } from './forms';
import type { GridSource } from './grids';
import { offsetOf } from './notes';
import { numbersOf, startOf } from './numbering';
import { outlineOf } from './outline';
import {
  breaksOf,
  clearOfParts,
  geometryOf,
  pageNumbers,
  pageNumbersOf,
  pagesPlugin,
  pagingOf,
  PX_PER_CM,
  sectionShown,
  sectionsOf,
  showPages,
  stackOf,
  type Geometry,
  type Laid,
  type PageSetup,
  type PartHeights,
  type Section,
} from './pages';
import { Papers, PartMeasures } from './Papers';
import { schema } from './schema';
import { settled } from './settled';
import type { Fields } from './parts';
import { showPaperPages } from './sheet';
import { decimalOf } from './stops';
import { stylingOf, type Styling } from './styling';
import { bodyOf } from './tab';
import { linesOf } from './tables';

type Tabs = readonly Pick<Tab, 'id' | 'title'>[];

/** The paper in whole CSS pixels, as the browser breaks printed pages: on a fraction of a pixel
 * more, each page's text would start that much higher than the last. */
function paperOf({ width, height }: PageSetup): { width: number; height: number; name: string } {
  const [across, down] = [width, height].map((cm) => Math.round(cm * PX_PER_CM));
  return { width: across, height: down, name: `paper-${across}-${down}` };
}

/** Each paper size by name, so a tab or a section on other paper starts a run of pages of its own. */
function pageRules(setups: readonly PageSetup[]): string {
  const papers = new Map(setups.map((setup) => [paperOf(setup).name, paperOf(setup)]));
  const size = ({ width, height }: { width: number; height: number }) =>
    `size: ${width}px ${height}px; margin: 0;`;
  return [
    `@page { ${size(paperOf(setups[0]))} }`,
    ...[...papers].map(([name, paper]) => `@page ${name} { ${size(paper)} }`),
  ].join('\n');
}

/** The ids of the section breaks in a tab's saved state. */
function breaksIn(state: Uint8Array): string[] {
  const saved = new Y.Doc();
  Y.applyUpdate(saved, state);
  const found = breaksOf(yXmlFragmentToProseMirrorRootNode(bodyOf(saved), schema));
  saved.destroy();
  return found;
}

interface Printing {
  own: Y.Doc;
  state: Uint8Array;
  grids: GridSource;
  tab: string;
  tabs: Tabs;
  home: string;
  styling: Styling;
  lists: ListStore;
  scope: string;
  fields: Fields;
  decimal: string;
  label: { current: (key: MessageKey) => string };
  locale: { current: DocumentLocale };
}

/** The tab's sections one after another, each on pages of its own paper, page numbers running on
 * through them from the tab's first unless a section starts its own. */
function PrintedTab({
  onLaid,
  ...printing
}: Printing & {
  /** The tab's pages were laid out again, `pages` of them. */
  onLaid: (tab: string, pages: number) => void;
}) {
  const { own, state, grids, tab, scope, fields, decimal } = printing;
  const sections = useMemo(() => sectionsOf(own, tab, breaksIn(state)), [own, tab, state]);
  const [heights, setHeights] = useState<PartHeights[]>([]);
  const keepHeights = useCallback(
    (next: PartHeights[]) =>
      setHeights((kept) => (JSON.stringify(kept) === JSON.stringify(next) ? kept : next)),
    [],
  );
  const sheets = useMemo(
    () =>
      sections.map(({ setup }, index) => {
        const paper = paperOf(setup);
        return clearOfParts(
          { ...geometryOf(setup), width: paper.width, height: paper.height, gap: 0 },
          heights[index] ?? {},
          setup.firstPage,
        );
      }),
    [sections, heights],
  );
  const [counts, setCounts] = useState<readonly number[]>([]);
  const counted = useRef<readonly number[]>([]);
  const sectionCount = useRef(sections.length);
  sectionCount.current = sections.length;
  const laidSection = useCallback(
    (section: number, pages: number) => {
      const next = [...counted.current];
      next[section] = pages;
      counted.current = next;
      setCounts((kept) => (kept[section] === pages ? kept : next));
      const all = next.slice(0, sectionCount.current);
      if (all.length === sectionCount.current && all.every((each) => each !== undefined)) {
        onLaid(
          tab,
          all.reduce((sum, each) => sum + each, 0),
        );
      }
    },
    [tab, onLaid],
  );
  const owners = useMemo(
    () => sections.flatMap((_, index) => Array<number>(counts[index] ?? 0).fill(index)),
    [sections, counts],
  );
  const numbers = useMemo(
    () =>
      pageNumbersOf(
        fields.first,
        sections.map(({ setup }) => setup),
        owners,
      ),
    [fields.first, sections, owners],
  );

  return (
    <>
      <PartMeasures
        sections={sections}
        fields={fields}
        decimal={decimal}
        scope={scope}
        grids={grids}
        onHeights={keepHeights}
      />
      {sections.map((_, index) => {
        const from = owners.indexOf(index);
        return (
          <PrintedSection
            key={index}
            {...printing}
            section={index}
            sections={sections}
            sheets={sheets}
            numbers={from < 0 ? [] : numbers.slice(from, from + counts[index])}
            last={index === sections.length - 1}
            onLaid={laidSection}
          />
        );
      })}
    </>
  );
}

/** A section of the tab on its pages: the tab's text with only the section's blocks shown, its
 * endnotes after the last section's. */
function PrintedSection({
  own,
  state,
  grids,
  tab,
  tabs,
  home,
  styling,
  lists,
  scope,
  fields,
  decimal,
  label,
  locale,
  section,
  sections,
  sheets,
  numbers,
  last,
  onLaid,
}: Printing & {
  section: number;
  sections: readonly Section[];
  sheets: readonly Geometry[];
  /** Each of the section's pages' number. */
  numbers: readonly number[];
  last: boolean;
  onLaid: (section: number, pages: number) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const notesHost = useRef<HTMLDivElement>(null);
  const paper = paperOf(sections[section].setup);
  const geometry = sheets[section];
  const laidOn = useMemo(() => sheets.map(() => geometry), [sheets, geometry]);
  const [view, setView] = useState<EditorView | null>(null);
  const [laid, setLaid] = useState<Laid | null>(null);
  const stack = useMemo(() => stackOf(laidOn, laid), [laidOn, laid]);

  useEffect(() => {
    const saved = new Y.Doc();
    Y.applyUpdate(saved, state);
    const ids = tabs.map(({ id }) => id);
    const contents = contentsStore(() => {});
    const view = savedView(host.current!, saved, {
      tab,
      grids,
      paper: true,
      notes: notesHost.current!,
      styling,
      lists,
      start: startOf(own, ids, tab),
      offset: offsetOf(own, ids, tab),
      follow: () => {},
      contents,
      label,
      locale,
      plugins: [pagesPlugin(), sectionShown(section)],
      printing: true,
      onState: (next) => {
        const laid = pagingOf(next)?.laid;
        if (!laid) return;
        setLaid(laid);
        onLaid(section, laid.pages);
      },
    });
    const { headings } = outlineOf(
      view.state.doc,
      null,
      numbersOf(view.state)!.labels,
      linesOf(grids),
    );
    contents.set(chaptersOf(own, tabs, { tab, headings }, styling, home));
    setView(view);
    return () => {
      view.destroy();
      saved.destroy();
    };
  }, [own, state, grids, tab, tabs, home, styling, lists, label, locale, section, onLaid]);

  useEffect(() => {
    if (view) showPages(view, laidOn);
  }, [view, laidOn]);

  const pages = laid?.pages ?? 1;
  return (
    <section
      className="ponistra-sheets ponistra-printed"
      data-pages={pages}
      data-height={paper.height}
      data-last={last || undefined}
      style={
        {
          width: paper.width,
          height: pages * paper.height,
          page: paper.name,
        } as CSSProperties
      }
    >
      <Papers
        stack={stack}
        sections={sections}
        numbers={numbers}
        fields={fields}
        decimal={decimal}
        scope={scope}
        writing={null}
        grids={grids}
      />
      <div
        data-styling={scope}
        style={
          {
            paddingTop: geometry.firstTop,
            paddingRight: geometry.right,
            paddingLeft: geometry.left,
            '--page-left': `${geometry.left}px`,
            '--page-right': `${geometry.right}px`,
          } as CSSProperties
        }
        className="ponistra-document ponistra-pages"
      >
        <div ref={host} />
        <div ref={notesHost} />
      </div>
    </section>
  );
}

/** Every tab of the document on its pages, one after another as the browser prints them, page
 * numbers running on through the tabs. `onReady` once the pages have stopped changing with their
 * fonts and images in. The tables' rows stand only on the pages printed: those the body's
 * `data-range` names, as `first-last` counted through all the tabs, which `data-ranged` repeats
 * once their fonts and images are in, else all of them as the browser prints. */
export default function PrintedDocument({
  own,
  tabs,
  states,
  grids,
  home,
  title,
  locale,
  onReady,
}: {
  own: Uint8Array;
  tabs: Tabs;
  /** Each tab's saved state, in the order of `tabs`. */
  states: readonly Uint8Array[];
  /** The grids of every table, the tabs' and the headers' and footers', whole. */
  grids: GridSource;
  home: string;
  title: string;
  locale: DocumentLocale;
  /** Called once laid out, with the count of each tab's pages by its id. */
  onReady: (pages: Record<string, number>) => void;
}) {
  const { t } = useI18n();
  const label = useRef(t);
  label.current = t;
  const localeNow = useRef(locale);
  localeNow.current = locale;
  const doc = useMemo(() => {
    const doc = new Y.Doc();
    Y.applyUpdate(doc, own);
    return doc;
  }, [own]);
  const styling = useMemo(() => stylingOf(doc), [doc]);
  const lists = useMemo(() => savedLists(formatsOf(doc)), [doc]);
  const { scope, sheet } = useStylesheet(styling);
  const ids = useMemo(() => tabs.map(({ id }) => id), [tabs]);
  const setups = useMemo(
    () =>
      ids.flatMap((id, index) =>
        sectionsOf(doc, id, breaksIn(states[index])).map(({ setup }) => setup),
      ),
    [doc, ids, states],
  );
  const [counts, setCounts] = useState<Record<string, number>>({});
  const changes = useRef(0);
  const onLaid = useCallback((tab: string, pages: number) => {
    changes.current += 1;
    setCounts((kept) => (kept[tab] === pages ? kept : { ...kept, [tab]: pages }));
  }, []);
  const { firsts, total } = useMemo(
    () => pageNumbers(doc, ids, (id) => counts[id] ?? 0),
    [doc, ids, counts],
  );
  const date = useMemo(() => writtenDate(new Date(), locale), [locale]);
  const decimal = decimalOf(locale);
  const fieldsOf = useMemo(() => {
    const fields = new Map<string, Fields>();
    for (const id of ids) fields.set(id, { first: firsts[id], total, title, date });
    return fields;
  }, [ids, firsts, total, title, date]);
  const laidAll = ids.every((id) => counts[id] !== undefined);
  const main = useRef<HTMLElement>(null);

  useEffect(() => {
    const { body } = document;
    const sections = () =>
      main.current!.querySelectorAll<HTMLElement>(':scope > .ponistra-printed');
    const observer = new MutationObserver(() => {
      const range = body.dataset.range ?? '';
      const [first, last] = range.split('-').map(Number);
      if (!(first >= 1 && last >= first)) return;
      let start = 1;
      for (const section of sections()) {
        const height = Number(section.dataset.height);
        const from = (first - start) * height;
        const to = (last - start + 1) * height;
        showPaperPages(section, (top, bottom) => bottom > from && top < to);
        start += Number(section.dataset.pages);
      }
      const images = [...document.images].map((image) => image.decode().catch(() => {}));
      Promise.all([document.fonts.ready, ...images]).then(() => {
        if (body.dataset.range === range) body.dataset.ranged = range;
      });
    });
    const whole = () => {
      if (body.dataset.range) return;
      for (const section of sections()) showPaperPages(section, () => true);
    };
    observer.observe(body, { attributes: true, attributeFilter: ['data-range'] });
    addEventListener('beforeprint', whole);
    return () => {
      observer.disconnect();
      removeEventListener('beforeprint', whole);
    };
  }, []);

  useEffect(() => {
    if (!laidAll) return;
    let gone = false;
    settled(changes, () => gone).then((done) => done && onReady(counts));
    return () => {
      gone = true;
    };
  }, [laidAll, counts, fieldsOf, onReady]);

  return (
    <main ref={main} className="ponistra-print">
      <style>{sheet}</style>
      <style>{pageRules(setups)}</style>
      {tabs.map(({ id }, index) => (
        <PrintedTab
          key={id}
          own={doc}
          state={states[index]}
          grids={grids}
          tab={id}
          tabs={tabs}
          home={home}
          styling={styling}
          lists={lists}
          scope={scope}
          fields={fieldsOf.get(id)!}
          decimal={decimal}
          label={label}
          locale={localeNow}
          onLaid={onLaid}
        />
      ))}
    </main>
  );
}
