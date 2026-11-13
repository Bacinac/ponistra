import type { PDFDocumentLoadingTask, RenderTask } from 'pdfjs-dist';
import { DOMSerializer, type Node } from 'prosemirror-model';
import { NodeSelection, Plugin, type EditorState } from 'prosemirror-state';
import type { Decoration, EditorView, NodeView } from 'prosemirror-view';
import { getJson, postBytes, postJson } from '../api';
import { watchNear } from '../near';
import { shortId } from './blocks';
import {
  imageFiles,
  insertBlocks,
  insertImages,
  resizeHandle,
  settle,
  shows,
  type ImageHost,
} from './images';
import { gapElement, PDF_PAGE, tableGaps, type TableGaps } from './pages';
import { pageOf, pdfSpec, pdfUrl, schema, widthOf } from './schema';
import { hold } from './settled';

const { pdf } = schema.nodes;
export const PDF_TYPE = 'application/pdf';
/** Where the printed document takes the page in, which the server reads from the link. */
const MARK = 'ponistra-pdf:';

/** What a block is made from: a file from the computer, one of the tree, or a PDF another
 * document shows. */
type Brought = File | { file: string } | { blob: string };
type Size = [width: number, height: number];

export interface PdfShown {
  waiting: string;
  unshown: string;
  /** Marks each page's place for the server to put the page in, rather than drawing it. */
  printing: boolean;
}

function link(host: ImageHost, body: Brought): Promise<{ blob: string }> {
  const path = `/api/nodes/${host.document}/pdfs`;
  return body instanceof Blob ? postBytes(path, body) : postJson(path, body);
}

/** Puts each PDF in as a block, at the drop or in place of the selection, its pages shown once
 * the server has it. */
export function insertPdfs(
  view: EditorView,
  host: ImageHost,
  brought: { body: Brought; title: string }[],
  at?: number,
) {
  if (!brought.length) return;
  const nodes = brought.map(({ title }) => pdf.create({ id: shortId(), title }));
  insertBlocks(view, nodes, at);
  nodes.forEach((node, index) =>
    link(host, brought[index].body).then(
      (linked) => settle(view, pdf, node.attrs.id, linked.blob),
      (error) => {
        settle(view, pdf, node.attrs.id, null);
        host.fail(error);
      },
    ),
  );
}

export function pdfFiles(files: FileList | undefined | null): File[] {
  return [...(files ?? [])].filter((file) => file.type === PDF_TYPE);
}

export function fromComputer(files: File[]): { body: Brought; title: string }[] {
  return files.map((file) => ({ body: file, title: file.name.replace(/\.pdf$/i, '') }));
}

export function pickPdfs(): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = PDF_TYPE;
    input.multiple = true;
    input.addEventListener('change', () => resolve(pdfFiles(input.files)));
    input.click();
  });
}

/** PDF files that come pasted or dropped, with the images among them, and the PDFs of other
 * PONISTRA documents, linked to this one too. */
export function pdfPasting(host: () => ImageHost): Plugin {
  const dropped = (view: EditorView, files: FileList | undefined | null, at?: number) => {
    const pdfs = pdfFiles(files);
    if (!pdfs.length) return false;
    insertImages(view, host(), imageFiles(files), at);
    insertPdfs(view, host(), fromComputer(pdfs), at);
    return true;
  };
  return new Plugin({
    props: {
      transformPasted(slice, view) {
        slice.content.descendants((node) => {
          const { blob } = node.attrs;
          if (node.type === pdf && blob && !shows(view.state, pdf, blob)) {
            link(host(), { blob }).catch(host().fail);
          }
        });
        return slice;
      },
      handlePaste(view, event) {
        if (event.clipboardData?.getData('text/plain').trim()) return false;
        return dropped(view, event.clipboardData?.files);
      },
      handleDrop(view, event, _slice, moved) {
        if (moved) return false;
        const at = view.posAtCoords({ left: event.clientX, top: event.clientY });
        return dropped(view, event.dataTransfer?.files, at?.pos ?? view.state.doc.content.size);
      },
    },
  });
}

export function selectedPdf(state: EditorState): { node: Node; pos: number } | null {
  const { selection } = state;
  return selection instanceof NodeSelection && selection.node.type === pdf
    ? { node: selection.node, pos: selection.from }
    : null;
}

/** The pages a block shows of the file's `count`, from its first to its last. */
export function shownPages(node: Node, count: number): { first: number; last: number } {
  const first = Math.min(pageOf(node.attrs.first) ?? 1, count);
  return { first, last: Math.max(first, Math.min(pageOf(node.attrs.last) ?? count, count)) };
}

const sizes = new Map<string, Promise<Size[]>>();

/** Each page's size in points as it shows, asked of the server once for each file. */
export function sizesOf(blob: string): Promise<Size[]> {
  let found = sizes.get(blob);
  if (!found) {
    found = getJson<{ pages: Size[] }>(`${pdfUrl(blob)}/pages`).then(({ pages }) => pages);
    found.catch(() => sizes.delete(blob));
    sizes.set(blob, found);
  }
  return found;
}

const opened = new Map<string, { task: Promise<PDFDocumentLoadingTask>; users: number }>();

/** The file opened by byte ranges, once however many blocks draw its pages. */
function openPdf(blob: string): Promise<PDFDocumentLoadingTask> {
  let found = opened.get(blob);
  if (!found) {
    found = { task: import('../pdf/load').then(({ load }) => load(pdfUrl(blob))), users: 0 };
    opened.set(blob, found);
  }
  found.users += 1;
  return found.task;
}

function closePdf(blob: string): void {
  const found = opened.get(blob);
  if (!found || --found.users > 0) return;
  opened.delete(blob);
  void found.task.then((task) => task.destroy());
}

/** A PDF in the editor: its pages one below another as wide as its frame, each drawn as it comes
 * near the view, or in print a link of its own the server puts the page in place of. */
export class PdfBlockView implements NodeView {
  dom: HTMLElement;
  private frame: HTMLElement | null = null;
  private handle: HTMLElement | null = null;
  private pages: HTMLElement[] = [];
  private gaps: TableGaps['rows'] = [];
  private gapElements: HTMLElement[] = [];
  private watcher: IntersectionObserver | null = null;
  private drawing = new Set<RenderTask>();
  private task: Promise<PDFDocumentLoadingTask> | null = null;
  private gone = false;

  constructor(
    private node: Node,
    view: EditorView,
    getPos: () => number | undefined,
    decorations: readonly Decoration[],
    private shown: PdfShown,
  ) {
    this.dom = DOMSerializer.renderSpec(document, pdfSpec(node)).dom as HTMLElement;
    this.dom.setAttribute('aria-label', String(node.attrs.title || 'PDF'));
    this.gaps = tableGaps(decorations);
    const blob = node.attrs.blob as string | null;
    if (!blob) {
      this.dom.dataset.waiting = shown.waiting;
      return;
    }
    const frame = document.createElement('div');
    frame.className = 'ponistra-frame';
    frame.style.width = `${widthOf(node.attrs.width) ?? 100}%`;
    this.dom.append(frame);
    this.frame = frame;
    if (!shown.printing) {
      this.handle = resizeHandle(view, getPos, () => this.node.attrs.align, this.dom, frame);
    }
    hold(
      sizesOf(blob).then(
        (found) => this.lay(blob, found),
        () => this.unshown(),
      ),
    );
  }

  private lay(blob: string, found: Size[]): void {
    if (this.gone || !found.length) return this.unshown();
    const { first, last } = shownPages(this.node, found.length);
    for (let number = first; number <= last; number++) {
      const [width, height] = found[number - 1];
      const page = document.createElement('div');
      page.className = PDF_PAGE;
      page.style.aspectRatio = `${width} / ${height}`;
      page.dataset.page = String(number);
      if (this.shown.printing) {
        const mark = document.createElement('a');
        mark.href = `${MARK}${blob}/${number}`;
        page.append(mark);
      }
      this.pages.push(page);
    }
    this.frame!.prepend(...this.pages);
    this.showGaps(this.gaps);
    if (this.shown.printing) return;
    this.watcher = watchNear(this.dom, (page) => void this.draw(blob, page as HTMLElement));
    for (const page of this.pages) this.watcher.observe(page);
  }

  private async draw(blob: string, page: HTMLElement): Promise<void> {
    this.task ??= openPdf(blob);
    try {
      const file = await (await this.task).promise;
      const proxy = await file.getPage(Number(page.dataset.page));
      if (this.gone) return;
      const natural = proxy.getViewport({ scale: 1 });
      const across = page.getBoundingClientRect().width * devicePixelRatio;
      const viewport = proxy.getViewport({ scale: across / natural.width });
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(viewport.width);
      canvas.height = Math.round(viewport.height);
      const drawn = proxy.render({ canvas, viewport });
      this.drawing.add(drawn);
      await drawn.promise.finally(() => this.drawing.delete(drawn));
      page.replaceChildren(canvas);
    } catch (error) {
      if (!this.gone && (error as Error | null)?.name !== 'RenderingCancelledException') {
        page.dataset.unshown = this.shown.unshown;
      }
    }
  }

  private unshown(): void {
    if (this.gone || !this.frame) return;
    this.frame.dataset.unshown = this.shown.unshown;
  }

  /** A gap of the given height before each page the paper's page starts with. */
  private showGaps(gaps: TableGaps['rows']): void {
    this.gaps = gaps;
    for (const gap of this.gapElements) gap.remove();
    this.gapElements = gaps.flatMap(({ row, gap }) => {
      const before = this.pages[row];
      if (!before) return [];
      const element = gapElement('block', gap);
      before.before(element);
      return [element];
    });
  }

  update(node: Node, decorations: readonly Decoration[]): boolean {
    if (!node.sameMarkup(this.node)) return false;
    this.node = node;
    const gaps = tableGaps(decorations);
    const same =
      gaps.length === this.gaps.length &&
      gaps.every((each, at) => each.row === this.gaps[at].row && each.gap === this.gaps[at].gap);
    if (!same) this.showGaps(gaps);
    return true;
  }

  stopEvent(event: Event): boolean {
    return event.target === this.handle;
  }

  ignoreMutation(): boolean {
    return true;
  }

  destroy(): void {
    this.gone = true;
    this.watcher?.disconnect();
    for (const drawn of this.drawing) drawn.cancel();
    if (this.task) closePdf(this.node.attrs.blob);
  }
}
