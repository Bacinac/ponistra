import type { PDFDocumentProxy } from 'pdfjs-dist';
import sandboxSource from 'pdfjs-dist/build/pdf.sandbox.min.mjs?url';
import type { EventBus } from 'pdfjs-dist/web/pdf_viewer.mjs';
import type * as Y from 'yjs';
import type { MessageKey } from '../i18n/hr';
import type { FileRoom } from './Notes';
import { OWN } from './notes';

/** A field's value as the file's room keeps it and the backend writes it into the file's copies
 * (apps/exports/annotated.py): its text, the option or options chosen, or the state of the box that
 * is on ('Off' for none); and its text as the field's own script shows it. */
export interface Filled {
  value: string | string[];
  shown?: string;
}

export function fieldsIn(doc: Y.Doc): Y.Map<Filled> {
  return doc.getMap<Filled>('fields');
}

export type Kind = 'text' | 'checkbox' | 'radiobutton' | 'combobox' | 'listbox';
const KINDS = new Set<string>(['text', 'checkbox', 'radiobutton', 'combobox', 'listbox']);

/** One of a field's widgets, with the state a box shows when it is on. */
export interface Widget {
  id: string;
  on: string | null;
}

export interface Field {
  name: string;
  kind: Kind;
  widgets: Widget[];
  many: boolean;
  /** Its value in the file as it came. */
  original: string | string[];
}

/** What pdf.js's getFieldObjects gives of each widget. */
export interface FieldObject {
  id: string;
  type: string;
  value?: unknown;
  exportValues?: unknown;
  multipleSelection?: boolean;
}

export function fieldsOf(objects: Map<string, FieldObject[]> | null): Map<string, Field> {
  const fields = new Map<string, Field>();
  for (const [name, all] of objects ?? []) {
    const kind = all.find((object) => KINDS.has(object.type))?.type as Kind | undefined;
    if (!kind) continue;
    const own = all.filter((object) => object.type === kind);
    const many = Boolean(own[0].multipleSelection);
    const { value } = own[0];
    const original =
      kind === 'checkbox' || kind === 'radiobutton'
        ? typeof value === 'string'
          ? value
          : 'Off'
        : many
          ? value == null
            ? []
            : [String(value)]
          : String(value ?? '');
    const widgets = own.map(({ id, exportValues }) => ({
      id,
      on: typeof exportValues === 'string' ? exportValues : null,
    }));
    fields.set(name, { name, kind, widgets, many, original });
  }
  return fields;
}

/** What a widget keeps in pdf.js's annotation storage while its field is filled so. */
export function storedFor(field: Field, widget: Widget, filled: Filled): Record<string, unknown> {
  const { value } = filled;
  if (field.kind === 'text') return { value, formattedValue: filled.shown ?? null };
  if (field.kind === 'checkbox' || field.kind === 'radiobutton') {
    return { value: value === widget.on };
  }
  return { value: Array.isArray(value) ? value : value ? [value] : [] };
}

/** A change pdf.js made to a field's widget: its text or choice, and the text as shown. */
export interface Touched {
  id: string;
  value?: unknown;
  shown?: string | null;
}

/** The field's value once `touched` reached it, its widgets keeping what `kept` reads. */
export function filledFrom(
  field: Field,
  touched: Touched,
  kept: (id: string) => unknown,
  before: Filled,
): Filled {
  if (field.kind === 'text') {
    const typed = 'value' in touched;
    const value = typed ? String(touched.value ?? '') : (before.value as string);
    const shown =
      'shown' in touched ? (touched.shown ?? undefined) : typed ? undefined : before.shown;
    return shown === undefined ? { value } : { value, shown };
  }
  if (field.kind === 'checkbox' || field.kind === 'radiobutton') {
    const on = field.widgets.find(
      (widget) => (kept(widget.id) ?? before.value === widget.on) === true,
    );
    return { value: on?.on ?? 'Off' };
  }
  const value = 'value' in touched ? touched.value : kept(touched.id);
  const chosen = Array.isArray(value)
    ? value.map(String)
    : value == null || value === ''
      ? []
      : [String(value)];
  return { value: field.many ? chosen : (chosen[0] ?? '') };
}

export function same(one: Filled, other: Filled): boolean {
  return (
    JSON.stringify(one.value) === JSON.stringify(other.value) &&
    (one.shown ?? null) === (other.shown ?? null)
  );
}

export interface SandboxEvent {
  id: string;
  name: string;
  [detail: string]: unknown;
}

/** The event that gives the file's scripts a value filled in elsewhere as if it had been typed
 * here, its own checks on typing aside, as those read text as typed and the room keeps the value;
 * null where the scripts know no such value, as a radio group with none chosen. */
export function settling(field: Field, filled: Filled): SandboxEvent | null {
  const { value } = filled;
  if (field.kind === 'text' || field.kind === 'combobox' || field.kind === 'listbox') {
    return { id: field.widgets[0].id, name: 'Validate', value };
  }
  const target = field.widgets.find((widget) => widget.on === value);
  if (field.kind === 'radiobutton' && !target) return null;
  return { id: (target ?? field.widgets[0]).id, name: 'Validate', value: value !== 'Off' };
}

export interface Say {
  t: (key: MessageKey) => string;
  formatNumber: (value: number) => string;
}

/** A message of pdf.js's own form scripts in the reader's language; others as the file says them. */
export function scriptMessage(text: string, { t, formatNumber }: Say): string {
  const number = (limit: string) => {
    const value = Number(limit);
    return Number.isFinite(value) ? formatNumber(value) : limit;
  };
  let found = /^The value entered does not match the format of the field (.*)$/.exec(text);
  if (found) return `${t('form.format')} ${found[1]}`;
  found =
    /^Invalid date \/ time: please ensure that the date \/ time exists\. Field (.*) should match format (.*)$/.exec(
      text,
    );
  if (found) return `${t('form.date')} ${found[1]}; ${t('form.date.as')} ${found[2]}`;
  found =
    /^Invalid value: must be greater than or equal to ?(.+?) and less than or equal to ?(.+?)\.$/.exec(
      text,
    );
  if (found)
    return `${t('form.between')} ${number(found[1])} ${t('form.and')} ${number(found[2])}.`;
  found = /^Invalid value: must be (greater|less) than or equal to ?(.+?)\.$/.exec(text);
  if (found) {
    return `${t(found[1] === 'greater' ? 'form.atLeast' : 'form.atMost')} ${number(found[2])}.`;
  }
  return text;
}

/** What pdf.js's QuickJS sandbox holds that the form needs. */
interface Sandbox {
  support: { win: unknown };
  create(data: unknown): void;
  dispatchEvent(event: unknown): void;
  nukeSandbox(): void;
}

/** What pdf.js's page view holds that the form needs. */
interface PageView {
  annotationLayer: { div: HTMLDivElement } | null;
  pdfPage: { getAnnotations(): Promise<Record<string, unknown>[]> } | null;
  viewport: {
    width: number;
    height: number;
    convertToViewportPoint(x: number, y: number): number[];
  };
}

function latch() {
  let resolve = () => {};
  const promise = new Promise<void>((done) => (resolve = done));
  return { promise, resolve: () => resolve() };
}

/** What the file's scripts reckon of themselves as the file opens, which nobody's undo takes back. */
const SETTLED = 'settled fields';
const WIDGET = 20;
/** A widget whose action leads somewhere pdf.js goes. */
const LEADS = ['url', 'dest', 'action', 'resetForm', 'setOCGState', 'attachment', 'actions'];

/** The file's form filled in its room: pdf.js draws its fields over the pages and keeps what is
 * typed in its annotation storage, which this keeps in step with the room both ways, and runs the
 * file's scripts in pdf.js's sandbox where the reader types. */
export class FormFill {
  private fields = new Map<string, Field>();
  private widgets = new Map<string, { field: Field; widget: Widget }>();
  private storage: PDFDocumentProxy['annotationStorage'] | null = null;
  private room: FileRoom | null = null;
  private editable = false;
  /** The file has scripts, which pdf.js's fields hand every key to. */
  private scripted = false;
  /** The file has signature fields, whose signatures a changed copy cannot keep. */
  signed = false;
  private unobserve: (() => void) | null = null;
  private applying = false;
  private touched = new Map<string, Touched>();
  /** Whose the values the sandbox sends now are; none while it learns values filled in elsewhere,
   * which the room already holds as they were reckoned there. */
  private origin: string | null = OWN;
  private sandbox: Sandbox | null = null;
  private queue: Promise<void> = Promise.resolve();
  /** Steps queued or running; while there are none, an event runs at once. */
  private busy = 0;
  private gone = false;
  private joined = latch();
  private known = latch();
  private controller = new AbortController();

  constructor(
    private readonly bus: EventBus,
    private readonly box: HTMLElement,
    private readonly wasm: string,
    private readonly say: Say,
    private readonly notice: (text: string) => void,
    private readonly pageView: (page: number) => unknown,
  ) {
    const { signal } = this.controller;
    bus.on('annotationlayerrendered', (event: { pageNumber: number }) => this.rendered(event), {
      signal,
    });
    box.addEventListener(
      'focusin',
      (event) => {
        if (!(event.target as Element).closest('[data-element-id]')) return;
        const begin = () => {
          this.flush();
          this.room?.undo.stopCapturing();
        };
        if (this.busy) this.later(begin);
        else begin();
      },
      { signal },
    );
  }

  /** Learns the file's fields and keeps what pdf.js stores of them. */
  async open(pdf: PDFDocumentProxy): Promise<void> {
    const [objects, { info }, scripted] = await Promise.all([
      pdf.getFieldObjects(),
      pdf.getMetadata(),
      pdf.hasJSActions(),
    ]);
    if (this.gone) return;
    this.scripted = scripted;
    const flags = info as { IsXFAPresent?: boolean; IsAcroFormPresent?: boolean };
    if (flags.IsXFAPresent && !flags.IsAcroFormPresent) this.notice(this.say.t('form.xfa'));
    const found =
      (objects as Map<string, FieldObject[]> | null) ?? new Map<string, FieldObject[]>();
    this.signed = [...found.values()].some((all) => all.some((each) => each.type === 'signature'));
    this.fields = fieldsOf(found);
    for (const field of this.fields.values()) {
      for (const widget of field.widgets) this.widgets.set(widget.id, { field, widget });
    }
    const storage = pdf.annotationStorage;
    const set = storage.setValue.bind(storage);
    storage.setValue = (key: string, value: Record<string, unknown>) => {
      const found = this.widgets.get(key);
      const button = found?.field.kind === 'checkbox' || found?.field.kind === 'radiobutton';
      // The sandbox gives a box not yet drawn its field's value, which pdf.js's radio button reads
      // inverted once drawn.
      if (found && button && typeof value.value === 'string') {
        value = { ...value, value: value.value === found.widget.on };
      }
      set(key, value);
      if (found && !this.applying) this.touch(found.field, key, value);
    };
    this.storage = storage;
    this.known.resolve();
    this.apply(this.fields.keys(), false);
  }

  /** Fills from the room, and into it where the reader may edit; until the room has synced the
   * fields take nothing. */
  attach(room: FileRoom | null, editable: boolean): void {
    this.editable = Boolean(room) && editable;
    this.lock();
    if (room === this.room) return;
    this.unobserve?.();
    this.unobserve = null;
    this.room = room;
    if (!room) return;
    const changed = (event: Y.YMapEvent<Filled>) => {
      const { origin } = event.transaction;
      if (origin !== OWN && origin !== SETTLED) this.apply(event.keysChanged, true);
    };
    room.fields.observe(changed);
    this.unobserve = () => room.fields.unobserve(changed);
    this.joined.resolve();
    this.apply(this.fields.keys(), this.sandbox !== null);
  }

  /** What pdf.js's scripting manager runs the file's scripts with. */
  scripting() {
    return {
      createSandbox: (data: { objects: Map<string, FieldObject[]> | null }) => {
        this.busy++;
        const made = this.queue.then(() => this.create(data)).finally(() => this.busy--);
        this.queue = made.catch(() => this.notice(this.say.t('form.failed')));
        return made;
      },
      dispatchEventInSandbox: (event: SandboxEvent) =>
        this.run([event], event.id === 'doc' || event.id === 'page' ? SETTLED : OWN),
      destroySandbox: () => {
        this.sandbox?.nukeSandbox();
        this.sandbox = null;
      },
    };
  }

  destroy(): void {
    this.gone = true;
    this.controller.abort();
    this.unobserve?.();
    this.sandbox?.nukeSandbox();
    this.sandbox = null;
  }

  private async create(data: { objects: Map<string, FieldObject[]> | null }): Promise<void> {
    await Promise.all([this.joined.promise, this.known.promise]);
    const { QuickJSSandbox } = (await import(/* @vite-ignore */ sandboxSource)) as {
      QuickJSSandbox: (wasmUrl: string) => Promise<Sandbox>;
    };
    const sandbox = await QuickJSSandbox(new URL(this.wasm, location.href).href);
    if (this.gone) {
      sandbox.nukeSandbox();
      return;
    }
    sandbox.support.win = this.window();
    const objects = [...(data.objects ?? [])].map(([name, all]): [string, FieldObject[]] => {
      const filled = this.room?.fields.get(name);
      return [name, filled ? all.map((object) => ({ ...object, value: filled.value })) : all];
    });
    sandbox.create({ ...data, objects: data.objects && new Map(objects) });
    this.sandbox = sandbox;
    this.lock();
  }

  /** The window the sandbox calls out to: its timers, and what it sends to pdf.js, without the
   * browser's blocking dialogs. */
  private window() {
    const say = (text: unknown) =>
      this.origin !== null &&
      typeof text === 'string' &&
      this.notice(scriptMessage(text, this.say));
    return {
      setTimeout: window.setTimeout.bind(window),
      clearTimeout: window.clearTimeout.bind(window),
      setInterval: window.setInterval.bind(window),
      clearInterval: window.clearInterval.bind(window),
      URL,
      console,
      CustomEvent,
      dispatchEvent: (event: CustomEvent<Record<string, unknown>>) => {
        this.sent(event.detail);
        return true;
      },
      alert: say,
      confirm: (text: unknown) => (say(text), false),
      prompt: (text: unknown) => (say(text), null),
    };
  }

  private sent(detail: Record<string, unknown>): void {
    if (this.origin === null && detail.id !== undefined) {
      const { value, formattedValue, selRange, focus, ...rest } = detail;
      if (Object.keys(rest).every((key) => key === 'id' || key === 'siblings')) return;
      detail = rest;
    }
    if (detail.id === undefined) {
      if (detail.command === 'println' || detail.command === 'clear') return;
      if (detail.command === 'error') this.notice(this.say.t('form.failed'));
      if (detail.command === 'print' || detail.command === 'SaveAs') {
        this.notice(this.say.t('form.action'));
        return;
      }
    }
    this.bus.dispatch('updatefromsandbox', { source: window, detail });
  }

  /** Runs the events in the sandbox after every event before them, at once where none waits, as
   * pdf.js reads a field's text for the next key only once the scripts gave back the last; then
   * writes once what they changed, so a total reckoned midway from a value not yet settled never
   * reaches the room. */
  private run(events: SandboxEvent[], origin: string | null): void {
    if (this.busy) this.later(() => this.step(events, origin));
    else this.step(events, origin);
  }

  private step(events: SandboxEvent[], origin: string | null): void {
    const sandbox = this.sandbox;
    if (!sandbox) return;
    this.busy++;
    this.origin = origin;
    try {
      for (const event of events) sandbox.dispatchEvent(event);
      if (origin === null) this.touched.clear();
      else this.flush();
    } finally {
      this.origin = OWN;
      this.busy--;
    }
  }

  private later(then: () => void): void {
    this.busy++;
    this.queue = this.queue.then(
      () =>
        new Promise<void>((done) =>
          setTimeout(() => {
            this.busy--;
            try {
              then();
            } finally {
              done();
            }
          }),
        ),
    );
  }

  private touch(field: Field, id: string, value: Record<string, unknown>): void {
    if (!this.editable) return;
    const touched = this.touched.get(field.name) ?? { id };
    touched.id = id;
    if ('value' in value) touched.value = value.value;
    if ('formattedValue' in value) touched.shown = value.formattedValue as string | null;
    this.touched.set(field.name, touched);
    queueMicrotask(() => this.flush());
  }

  private flush(): void {
    const room = this.room;
    const storage = this.storage;
    const origin = this.origin;
    if (!this.touched.size || !room || !storage || origin === null) return;
    const touched = [...this.touched.entries()];
    this.touched.clear();
    const kept = (id: string) =>
      (storage.getRawValue(id) as { value?: unknown } | undefined)?.value;
    const changes: [string, Filled][] = [];
    for (const [name, touch] of touched) {
      const field = this.fields.get(name)!;
      const entry = room.fields.get(name);
      const before = entry ?? { value: field.original };
      const after = filledFrom(field, touch, kept, before);
      if (same(after, before)) continue;
      if (!entry && same({ value: after.value }, { value: field.original })) continue;
      changes.push([name, after]);
    }
    if (!changes.length) return;
    room.fill((fields) => {
      for (const [name, filled] of changes) fields.set(name, filled);
    }, origin);
  }

  /** Shows the room's values in pdf.js's storage and its fields, and when they came from elsewhere
   * after the file's scripts started, gives them to the scripts too. */
  private apply(names: Iterable<string>, settle: boolean): void {
    const room = this.room;
    const storage = this.storage;
    if (!room || !storage) return;
    const events: SandboxEvent[] = [];
    this.applying = true;
    try {
      for (const name of names) {
        const field = this.fields.get(name);
        if (!field) {
          console.error(`The file has no field ${name}`);
          continue;
        }
        const filled = room.fields.get(name) ?? { value: field.original };
        for (const widget of field.widgets) {
          storage.setValue(widget.id, storedFor(field, widget, filled));
          this.show(widget, filled);
        }
        const event = settle && settling(field, filled);
        if (event) events.push(event);
      }
    } finally {
      this.applying = false;
    }
    if (events.length) this.run(events, null);
  }

  private show(widget: Widget, filled: Filled): void {
    const element = this.box.querySelector(`[data-element-id="${CSS.escape(widget.id)}"]`);
    if (
      element instanceof HTMLInputElement &&
      (element.type === 'checkbox' || element.type === 'radio')
    ) {
      element.checked = filled.value === widget.on;
    } else if (element instanceof HTMLSelectElement) {
      const chosen = Array.isArray(filled.value) ? filled.value : [filled.value];
      element.selectedIndex = -1;
      for (const option of element.options) option.selected = chosen.includes(option.value);
    } else if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const text = filled.value as string;
      element.value = element === document.activeElement ? text : (filled.shown ?? text);
      element.dispatchEvent(
        new CustomEvent('updatefromsandbox', {
          detail: { value: text, formattedValue: filled.shown ?? null },
        }),
      );
    }
  }

  /** Readers, and everyone until the room has synced and the file's scripts have started, see the
   * fields but cannot change them. */
  private lock(root: ParentNode = this.box): void {
    const open = this.editable && (!this.scripted || this.sandbox !== null);
    for (const element of root.querySelectorAll<HTMLInputElement>(
      'input[data-element-id], textarea[data-element-id], select[data-element-id]',
    )) {
      if (!open && !element.disabled) {
        element.disabled = true;
        element.dataset.locked = '';
      } else if (open && element.dataset.locked !== undefined) {
        element.disabled = false;
        delete element.dataset.locked;
      }
    }
  }

  private async rendered({ pageNumber }: { pageNumber: number }): Promise<void> {
    const view = this.pageView(pageNumber) as PageView | undefined;
    const layer = view?.annotationLayer?.div;
    const page = view?.pdfPage;
    if (!view || !layer || !page) return;
    this.lock(layer);
    const annotations = await page.getAnnotations();
    const { width, height } = view.viewport;
    for (const annotation of annotations) {
      if (annotation.annotationType !== WIDGET) continue;
      const id = annotation.id as string;
      if (layer.querySelector(`[data-blocked="${CSS.escape(id)}"]`)) continue;
      if (annotation.fieldType === 'Sig') {
        const [left, bottom, right, top] = annotation.rect as number[];
        const [x0, y0] = view.viewport.convertToViewportPoint(left, bottom);
        const [x1, y1] = view.viewport.convertToViewportPoint(right, top);
        const marker = document.createElement('section');
        Object.assign(marker.style, {
          left: `${(Math.min(x0, x1) / width) * 100}%`,
          top: `${(Math.min(y0, y1) / height) * 100}%`,
          width: `${(Math.abs(x1 - x0) / width) * 100}%`,
          height: `${(Math.abs(y1 - y0) / height) * 100}%`,
        });
        this.block(marker, id, this.say.t('form.signature'));
        layer.append(marker);
      } else if (
        annotation.pushButton &&
        !annotation.isTooltipOnly &&
        !LEADS.some((key) => annotation[key])
      ) {
        const button = layer.querySelector<HTMLElement>(`[data-annotation-id="${CSS.escape(id)}"]`);
        if (button) this.block(button, id, this.say.t('form.action'));
      }
    }
  }

  private block(element: HTMLElement, id: string, note: string): void {
    element.classList.add('ponistra-blocked');
    element.dataset.blocked = id;
    element.title = note;
    element.setAttribute('aria-label', note);
    element.setAttribute('aria-disabled', 'true');
  }
}
