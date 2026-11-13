import { DOMSerializer, Fragment, type Node } from 'prosemirror-model';
import type { EditorView } from 'prosemirror-view';
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { yXmlFragmentToProseMirrorRootNode } from 'y-prosemirror';
import * as Y from 'yjs';
import { useI18n } from '../i18n';
import type { DocumentLocale, Tab } from '../tree';
import { contentsStore } from './contents';
import { Frames } from './Deck';
import {
  dealingOf,
  deckPlugin,
  measuredSlides,
  showDeck,
  type Deck,
  type MeasuredSlide,
} from './deck';
import { savedView, useStylesheet } from './Editor';
import type { GridSource } from './grids';
import { writtenDate } from './formats';
import { formatsOf, savedLists, type ListStore } from './forms';
import { offsetOf } from './notes';
import { startOf } from './numbering';
import { PX_PER_CM } from './pages';
import { schema } from './schema';
import { firstsOf, runOf, type Shown } from './show';
import { slidesOf, templateOf, type Template } from './slides';
import { stylingOf, type Styling } from './styling';
import { bodyOf } from './tab';

/** The document as a show reads it: saved, every tab's slides in reading order. */
export interface Shows {
  own: Y.Doc;
  grids: GridSource;
  ids: string[];
  tabs: { id: string; saved: Y.Doc; doc: Node }[];
  run: Shown[];
  firsts: Record<string, number>;
  styling: Styling;
  lists: ListStore;
  template: Template;
  locale: DocumentLocale;
  date: string;
  scope: string;
  sheet: string;
}

export function useShows(
  own: Uint8Array,
  tabs: readonly Pick<Tab, 'id'>[],
  states: readonly Uint8Array[],
  grids: GridSource,
  locale: DocumentLocale,
): Shows {
  const read = useMemo(() => {
    const doc = new Y.Doc();
    Y.applyUpdate(doc, own);
    const shown = tabs.map(({ id }, at) => {
      const saved = new Y.Doc();
      Y.applyUpdate(saved, states[at]);
      return { id, saved, doc: yXmlFragmentToProseMirrorRootNode(bodyOf(saved), schema) };
    });
    const run = runOf(shown);
    return {
      own: doc,
      grids,
      ids: tabs.map(({ id }) => id),
      tabs: shown,
      run,
      firsts: firstsOf(run),
      styling: stylingOf(doc),
      lists: savedLists(formatsOf(doc)),
      template: templateOf(doc),
    };
  }, [own, tabs, states, grids]);
  const { scope, sheet } = useStylesheet(read.styling);
  const date = useMemo(() => writtenDate(new Date(), locale), [locale]);
  return useMemo(
    () => ({ ...read, locale, date, scope, sheet }),
    [read, locale, date, scope, sheet],
  );
}

/** How large an element is, as it changes. */
export function useBox(ref: RefObject<HTMLElement | null>): { width: number; height: number } {
  const [box, setBox] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current!;
    const read = () =>
      setBox((was) =>
        was.width === element.clientWidth && was.height === element.clientHeight
          ? was
          : { width: element.clientWidth, height: element.clientHeight },
      );
    const observer = new ResizeObserver(read);
    observer.observe(element);
    read();
    return () => observer.disconnect();
  }, [ref]);
  return box;
}

/** A tab's slides laid out as the Slides view lays them, read only, showing the one at `index`
 * as large as fits `width` by `height`, or none while kept laid out for when it is shown. Each time
 * they are laid out, `onLaid` can measure them. */
export function TabDeck({
  shows,
  tab,
  index,
  width,
  height,
  onLaid,
}: {
  shows: Shows;
  tab: string;
  index: number | null;
  width: number;
  height: number;
  onLaid?: (tab: string, measured: () => MeasuredSlide[]) => void;
}) {
  const { t } = useI18n();
  const label = useRef(t);
  label.current = t;
  const locale = useRef(shows.locale);
  locale.current = shows.locale;
  const host = useRef<HTMLDivElement>(null);
  const notesHost = useRef<HTMLDivElement>(null);
  const [deck, setDeck] = useState<Deck | null>(null);
  const laid = useRef(onLaid);
  laid.current = onLaid;
  const saved = shows.tabs.find((each) => each.id === tab)!.saved;
  const { own, grids, ids, styling, lists, template } = shows;

  useEffect(() => {
    const view: EditorView = savedView(host.current!, saved, {
      tab,
      grids,
      notes: notesHost.current!,
      styling,
      lists,
      start: startOf(own, ids, tab),
      offset: offsetOf(own, ids, tab),
      follow: () => {},
      contents: contentsStore(() => {}),
      label,
      locale,
      plugins: [deckPlugin()],
      onState: (state) => {
        const dealt = dealingOf(state)?.deck ?? null;
        setDeck(dealt);
        if (dealt) laid.current?.(tab, () => measuredSlides(view, dealt, template));
      },
    });
    showDeck(view, template);
    return () => view.destroy();
  }, [saved, own, grids, ids, tab, styling, lists, template]);

  const across = template.size.width * PX_PER_CM;
  const down = template.size.height * PX_PER_CM;
  const scale = Math.min(width / across, height / down) || 0;
  const shown = index === null ? undefined : deck?.slides[index];
  return (
    <div className="ponistra-stage" style={{ visibility: shown ? undefined : 'hidden' }}>
      <div
        className="ponistra-stage-slide"
        style={{
          left: (width - across * scale) / 2,
          top: (height - down * scale) / 2,
          width: across * scale,
          height: down * scale,
        }}
      >
        <div
          className="ponistra-sheets"
          style={{
            width: across,
            transform: `translateY(${-(shown?.top ?? 0) * scale}px) scale(${scale})`,
          }}
        >
          {deck && (
            <Frames
              deck={deck}
              cursor={null}
              editable={false}
              date={shows.date}
              scope={shows.scope}
              first={shows.firsts[tab] ?? 0}
            />
          )}
          <div data-styling={shows.scope} className="ponistra-document ponistra-slides">
            <div ref={host} />
            <div ref={notesHost} />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Every tab's slides, the one at the show's place `at` in sight. */
export function Stage({ shows, at }: { shows: Shows; at: number }) {
  const around = useRef<HTMLDivElement>(null);
  const { width, height } = useBox(around);
  const shown = shows.run[at];
  return (
    <div ref={around} className="relative h-full w-full">
      {shows.tabs.map(({ id }) => (
        <TabDeck
          key={id}
          shows={shows}
          tab={id}
          index={shown?.tab === id ? shown.index : null}
          width={width}
          height={height}
        />
      ))}
    </div>
  );
}

/** The speaker notes of the slide at the show's place `at`, as written. */
export function SpeakerNotes({ shows, at }: { shows: Shows; at: number }) {
  const into = useRef<HTMLDivElement>(null);
  const shown = shows.run[at];
  const notes = useMemo(() => {
    if (!shown) return [];
    const { doc } = shows.tabs.find((each) => each.id === shown.tab)!;
    return slidesOf(doc)[shown.index]?.notes.map(({ node }) => node) ?? [];
  }, [shows, shown]);
  useEffect(() => {
    const serializer = DOMSerializer.fromSchema(schema);
    into.current!.replaceChildren(
      serializer.serializeFragment(
        Fragment.from(
          notes.map((node) => node.type.create({ ...node.attrs, speaker: false }, node.content)),
        ),
      ),
    );
  }, [notes]);
  return <div ref={into} className="ponistra-speaking" />;
}
