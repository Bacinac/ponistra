import type { Node } from 'prosemirror-model';
import { Plugin, PluginKey, type Command, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import { reshape } from './blocks';
import { PX_PER_CM, scaleOf } from './pages';
import { STOP_NEAR, stopsOf, type Leader, type TabStop } from './schema';

/** Word's default stops, every 1.25 cm past a paragraph's own. */
export const DEFAULT_STOP = 1.25;

export const near = (stop: TabStop, at: number) => Math.abs(stop.at - at) < STOP_NEAR;

/** Changes the stops of every selected paragraph; one the change leaves as it was is not
 * touched. */
function changeStops(change: (stops: TabStop[]) => TabStop[]): Command {
  return reshape((attrs) => {
    const before = stopsOf(attrs.tabs);
    const after = stopsOf(change(before));
    if (JSON.stringify(after) === JSON.stringify(before)) return null;
    return { tabs: after.length ? after : null };
  });
}

export function addStop(stop: TabStop): Command {
  return changeStops((stops) => [...stops.filter((each) => !near(each, stop.at)), stop]);
}

export function moveStop(from: number, to: number): Command {
  return changeStops((stops) => {
    const moved = stops.find((each) => near(each, from));
    if (!moved) return stops;
    return [...stops.filter((each) => each !== moved && !near(each, to)), { ...moved, at: to }];
  });
}

export function removeStop(at: number): Command {
  return changeStops((stops) => stops.filter((each) => !near(each, at)));
}

export function restyleStop(at: number, patch: Partial<Omit<TabStop, 'at'>>): Command {
  return changeStops((stops) =>
    stops.map((each) => (near(each, at) ? { ...each, ...patch } : each)),
  );
}

const same = (a: TabStop, b: TabStop) =>
  a.at === b.at && a.kind === b.kind && a.leader === b.leader;

/** What was made of `before`, the first selected paragraph's stops, as `after`, done to every
 * selected paragraph as Word's Tabs dialog does: the stops cleared go, the stops set take their
 * places, and a paragraph's other stops stay. */
export function retab(before: readonly TabStop[], after: readonly TabStop[]): Command {
  const cleared = before.filter((stop) => !after.some((each) => near(each, stop.at)));
  const set = after.filter((stop) => !before.some((each) => same(each, stop)));
  const gone = [...cleared, ...set];
  return changeStops((stops) => [
    ...stops.filter((each) => !gone.some((stop) => near(stop, each.at))),
    ...set,
  ]);
}

/** The decimal separator of a language, which a decimal stop lines numbers up on. */
export function decimalOf(locale: string): string {
  return (
    new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')
      ?.value ?? '.'
  );
}

export interface LaidTab {
  width: number;
  leader: Leader | null;
}

/** Where a tab starting this far along runs to, in px from the text's left edge: the next of the
 * paragraph's stops, its hanging indent where the first line hangs, or Word's next default. */
function nextStop(x: number, stops: readonly TabStop[], hanging: number | null): TabStop {
  const past = x + 0.5;
  const own = stops.find((stop) => stop.at * PX_PER_CM > past);
  if (hanging !== null && hanging > past && (!own || hanging < own.at * PX_PER_CM)) {
    return { at: hanging / PX_PER_CM, kind: 'left' };
  }
  if (own) return own;
  const step = DEFAULT_STOP * PX_PER_CM;
  return { at: ((Math.floor(past / step) + 1) * step) / PX_PER_CM, kind: 'left' };
}

/** How wide what follows a tab is on its line, up to the next tab or, for a decimal stop, to
 * the decimal separator, in px as the screen shows it. */
function following(
  paragraph: HTMLElement,
  tab: HTMLElement,
  next: HTMLElement | undefined,
  separator: string | null,
): number {
  const range = document.createRange();
  range.setStartAfter(tab);
  if (next) range.setEndBefore(next);
  else range.setEnd(paragraph, paragraph.childNodes.length);
  if (separator) {
    const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
    for (let text = walker.nextNode(); text; text = walker.nextNode()) {
      if (!range.intersectsNode(text) || tab.contains(text)) continue;
      const found = text.textContent!.indexOf(separator);
      if (found >= 0) {
        range.setEnd(text, found);
        break;
      }
    }
  }
  const line = tab.getBoundingClientRect();
  let width = 0;
  for (const rect of range.getClientRects()) {
    if (Math.abs(rect.top - line.top) < line.height / 2) width += rect.width;
  }
  return width;
}

/** How wide each of a paragraph's tabs runs, each to the next stop past where it starts: what
 * follows starts at a left stop, is centred on a centre one, ends at a right one and has its
 * decimal separator at a decimal one. */
export function laidTabs(
  paragraph: HTMLElement,
  tabs: readonly HTMLElement[],
  decimal: string,
): LaidTab[] {
  const box = paragraph.getBoundingClientRect();
  const scale = scaleOf(paragraph, box);
  const style = getComputedStyle(paragraph);
  const inset = parseFloat(style.getPropertyValue('--inset-left')) || 0;
  const origin = box.left - (parseFloat(style.marginLeft) - inset) * scale;
  let stops: TabStop[] = [];
  try {
    stops = stopsOf(JSON.parse(paragraph.dataset.tabs ?? 'null'));
  } catch {
    stops = [];
  }
  const indent = (Number(paragraph.dataset.indent) || 0) * PX_PER_CM;
  const hanging = (Number(paragraph.dataset.firstLine) || 0) < 0 ? indent : null;
  const laid: LaidTab[] = [];
  let line = NaN;
  let shift = 0;
  tabs.forEach((tab, index) => {
    const rect = tab.getBoundingClientRect();
    if (!(Math.abs(rect.top - line) < rect.height / 2)) {
      line = rect.top;
      shift = 0;
    }
    const x = (rect.left - origin) / scale + shift;
    const stop = nextStop(x, stops, hanging);
    const room = stop.at * PX_PER_CM - x;
    const after =
      stop.kind === 'left'
        ? 0
        : following(paragraph, tab, tabs[index + 1], stop.kind === 'decimal' ? decimal : null) /
          scale;
    const width = Math.max(0, stop.kind === 'center' ? room - after / 2 : room - after);
    laid.push({ width, leader: stop.leader ?? null });
    shift += width - (parseFloat(tab.style.paddingRight) || 0);
  });
  return laid;
}

function paragraphOf(tab: HTMLElement): HTMLElement | null {
  return tab.parentElement?.closest<HTMLElement>('p, h1, h2, h3, h4, h5, h6') ?? null;
}

/** The tabs under a root grouped by their paragraph, in order. */
function grouped(tabs: Iterable<HTMLElement>): Map<HTMLElement, HTMLElement[]> {
  const groups = new Map<HTMLElement, HTMLElement[]>();
  for (const tab of tabs) {
    const paragraph = paragraphOf(tab);
    if (!paragraph) continue;
    groups.set(paragraph, [...(groups.get(paragraph) ?? []), tab]);
  }
  return groups;
}

function shown(tab: HTMLElement, { width, leader }: LaidTab): void {
  tab.style.paddingRight = `${width}px`;
  if (leader) tab.dataset.leader = leader;
  else delete tab.dataset.leader;
}

/** Lays out the tabs of rendered text no editor keeps, as a header shows on its pages. */
export function layTabs(root: HTMLElement, decimal: string): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  for (let text = walker.nextNode(); text; text = walker.nextNode()) {
    if (text.textContent!.includes('\t')) texts.push(text as Text);
  }
  for (let text of texts) {
    for (let found = text.data.indexOf('\t'); found >= 0; found = text.data.indexOf('\t')) {
      const tab = text.splitText(found);
      text = tab.splitText(1);
      const wrap = document.createElement('span');
      wrap.className = 'ponistra-tab';
      tab.replaceWith(wrap);
      wrap.append(tab);
    }
  }
  const groups = grouped(root.querySelectorAll<HTMLElement>('.ponistra-tab'));
  for (let pass = 0; pass < 2; pass++) {
    for (const [paragraph, tabs] of groups) {
      laidTabs(paragraph, tabs, decimal).forEach((laid, index) => shown(tabs[index], laid));
    }
  }
}

interface TabState {
  laid: ReadonlyMap<number, LaidTab>;
  decorations: DecorationSet;
}

const tabKey = new PluginKey<TabState>('tabStops');
/** Layouts in a row that each move what the one before laid out, which may not run on for ever. */
const PASSES = 4;

function decorated(doc: Node, laid: ReadonlyMap<number, LaidTab>): DecorationSet {
  const found: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (!node.isText) return true;
    const text = node.text!;
    for (let index = text.indexOf('\t'); index >= 0; index = text.indexOf('\t', index + 1)) {
      const at = pos + index;
      const { width, leader } = laid.get(at) ?? { width: 0, leader: null };
      found.push(
        Decoration.inline(at, at + 1, {
          class: 'ponistra-tab',
          style: `padding-right: ${width}px`,
          ...(leader && { 'data-leader': leader }),
        }),
      );
    }
    return false;
  });
  return DecorationSet.create(doc, found);
}

function changed(before: ReadonlyMap<number, LaidTab>, after: ReadonlyMap<number, LaidTab>) {
  if (before.size !== after.size) return true;
  for (const [pos, laid] of after) {
    const was = before.get(pos);
    if (!was || Math.abs(was.width - laid.width) > 0.5 || was.leader !== laid.leader) return true;
  }
  return false;
}

class TabLayout {
  private frame = 0;
  private passes = 0;
  private width = 0;
  private observer: ResizeObserver | null = null;
  private fonts = () => this.schedule(true);

  constructor(
    private view: EditorView,
    private decimal: () => string,
  ) {
    this.watch();
  }

  update(view: EditorView, previous: EditorState): void {
    if (view.state.doc !== previous.doc) {
      this.watch();
      this.schedule(true);
    } else if (tabKey.getState(view.state) !== tabKey.getState(previous)) this.schedule(false);
  }

  /** Lays the tabs out again when the text's width or fonts change, while there are tabs. */
  private watch(): void {
    const on = tabKey.getState(this.view.state)!.decorations.find().length > 0;
    if (on && !this.observer) {
      this.width = this.view.dom.clientWidth;
      this.observer = new ResizeObserver(() => {
        if (this.view.dom.clientWidth === this.width) return;
        this.width = this.view.dom.clientWidth;
        this.schedule(true);
      });
      this.observer.observe(this.view.dom);
      document.fonts?.addEventListener('loadingdone', this.fonts);
      this.schedule(true);
    } else if (!on && this.observer) {
      this.observer.disconnect();
      this.observer = null;
      document.fonts?.removeEventListener('loadingdone', this.fonts);
    }
  }

  private schedule(fresh: boolean): void {
    if (fresh) this.passes = 0;
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => this.lay());
  }

  private lay(): void {
    const view = this.view;
    if (view.isDestroyed) return;
    const current = tabKey.getState(view.state)!;
    if (this.passes >= PASSES || !this.observer) return;
    const tabs = [...view.dom.querySelectorAll<HTMLElement>('.ponistra-tab')].filter(
      (tab) => tab.closest('.ProseMirror') === view.dom,
    );
    const laid = new Map<number, LaidTab>();
    for (const [paragraph, group] of grouped(tabs)) {
      laidTabs(paragraph, group, this.decimal()).forEach((each, index) =>
        laid.set(view.posAtDOM(group[index], 0), each),
      );
    }
    if (!changed(current.laid, laid)) return;
    this.passes += 1;
    view.dispatch(view.state.tr.setMeta(tabKey, laid).setMeta('addToHistory', false));
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.observer?.disconnect();
    document.fonts?.removeEventListener('loadingdone', this.fonts);
  }
}

/** Tabs run to their paragraph's stops, as Word lays them out: the editor measures them once the
 * browser has laid the text out, and again when the text, its width or its fonts change. */
export function tabStops(decimal: () => string): Plugin<TabState> {
  return new Plugin<TabState>({
    key: tabKey,
    state: {
      init: (_, state) => ({ laid: new Map(), decorations: decorated(state.doc, new Map()) }),
      apply(tr, previous) {
        const laid = tr.getMeta(tabKey) as ReadonlyMap<number, LaidTab> | undefined;
        if (laid) return { laid, decorations: decorated(tr.doc, laid) };
        if (!tr.docChanged) return previous;
        const mapped = new Map<number, LaidTab>();
        for (const [pos, each] of previous.laid) mapped.set(tr.mapping.map(pos), each);
        return { laid: mapped, decorations: decorated(tr.doc, mapped) };
      },
    },
    props: { decorations: (state) => tabKey.getState(state)!.decorations },
    view: (view) => new TabLayout(view, decimal),
  });
}
