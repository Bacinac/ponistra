import { DOMSerializer, Fragment, Slice, type Node, type NodeType } from 'prosemirror-model';
import { NodeSelection, Plugin, type EditorState } from 'prosemirror-state';
import { insertPoint } from 'prosemirror-transform';
import type { EditorView, NodeView } from 'prosemirror-view';
import { postBytes, postJson } from '../api';
import type { MessageKey } from '../i18n/hr';
import { IMAGE_ACCEPT } from '../upload';
import { shortId } from './blocks';
import { blobOf, imageSpec, schema, widthOf } from './schema';
import { outerOf } from './tableBase';

const { image, paragraph } = schema.nodes;
const FETCHED = /^(?:https?:|data:image\/)/i;

interface Linked {
  blob: string;
  media_type: string;
}

export interface ImageHost {
  document: string;
  fail: (error: unknown) => void;
  label: (key: MessageKey) => string;
}

export function placed(
  state: EditorState,
  type: NodeType,
  id: string,
): { node: Node; pos: number } | null {
  let found: { node: Node; pos: number } | null = null;
  state.doc.descendants((node, pos) => {
    if (node.type === type && node.attrs.id === id) found = { node, pos };
    return !found;
  });
  return found;
}

export function shows(state: EditorState, type: NodeType, blob: string): boolean {
  let found = false;
  state.doc.descendants((node) => {
    found ||= node.type === type && node.attrs.blob === blob;
    return !found;
  });
  return found;
}

/** The placeholder shows the image or the PDF once the server has it, and goes if it never
 * will. */
export function settle(view: EditorView, type: NodeType, id: string, blob: string | null): void {
  const found = !view.isDestroyed && placed(view.state, type, id);
  if (!found) return;
  const tr = view.state.tr.setMeta('addToHistory', false);
  view.dispatch(
    blob
      ? tr.setNodeAttribute(found.pos, 'blob', blob)
      : tr.delete(found.pos, found.pos + found.node.nodeSize),
  );
}

type Brought = Blob | { blob: string } | { url: string } | { file: string };

/** Stores the image, or links one the server has already, as one the document shows. */
function link(host: ImageHost, body: Brought): Promise<Linked> {
  const path = `/api/nodes/${host.document}/images`;
  return body instanceof Blob ? postBytes<Linked>(path, body) : postJson<Linked>(path, body);
}

function adopt(view: EditorView, host: ImageHost, id: string, body: Promise<Brought>) {
  const outer = outerOf(view);
  body
    .then((found) => link(host, found))
    .then(
      (linked) => settle(outer, image, id, linked.blob),
      (error) => {
        settle(outer, image, id, null);
        host.fail(error);
      },
    );
}

export function imageFiles(files: FileList | undefined | null): File[] {
  return [...(files ?? [])].filter((file) => file.type.startsWith('image/'));
}

/** Puts the blocks in, at the drop or in place of the selection, with a paragraph after the
 * last to write on. */
export function insertBlocks(view: EditorView, nodes: Node[], at?: number) {
  const content = Fragment.from(nodes);
  const tr = view.state.tr;
  if (at === undefined) tr.replaceSelection(new Slice(content, 0, 0));
  else tr.insert(insertPoint(tr.doc, at, nodes[0].type) ?? tr.doc.content.size, content);
  if (!tr.doc.lastChild!.isTextblock) tr.insert(tr.doc.content.size, paragraph.create());
  view.dispatch(tr.scrollIntoView());
}

/** Puts the files in as images, at the drop or in place of the selection. */
export function insertImages(view: EditorView, host: ImageHost, files: File[], at?: number) {
  if (!files.length) return;
  const nodes = files.map(() => image.create({ id: shortId() }));
  insertBlocks(view, nodes, at);
  nodes.forEach((node, index) => adopt(view, host, node.attrs.id, Promise.resolve(files[index])));
}

/** Puts in, in place of the selection, the picture a file of the folders holds. */
export function insertImageFile(view: EditorView, host: ImageHost, file: string) {
  const node = image.create({ id: shortId() });
  insertBlocks(view, [node]);
  adopt(view, host, node.attrs.id, Promise.resolve({ file }));
}

export function pickImages(): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = IMAGE_ACCEPT;
    input.multiple = true;
    input.addEventListener('change', () => resolve(imageFiles(input.files)));
    input.click();
  });
}

/** Images that come pasted or dropped: files are stored, pictures from the web fetched by the
 * server, and those of other PONISTRA documents linked to this one too. */
export function imagePasting(host: () => ImageHost): Plugin {
  const pending = new Map<string, string>();
  return new Plugin({
    props: {
      transformPastedHTML(html) {
        const parsed = new DOMParser().parseFromString(html, 'text/html');
        let local = 0;
        for (const img of parsed.body.querySelectorAll('img')) {
          const src = img.getAttribute('src') ?? '';
          if (blobOf(src)) continue;
          if (FETCHED.test(src)) {
            img.dataset.imageId = shortId();
            pending.set(img.dataset.imageId, src);
          } else {
            img.remove();
            local += 1;
          }
        }
        if (local) host().fail(new Error(host().label('image.local')));
        return parsed.body.innerHTML;
      },
      transformPasted(slice, view) {
        slice.content.descendants((node) => {
          if (node.type !== image) return;
          const { id, blob } = node.attrs;
          const src = pending.get(id);
          if (src !== undefined) {
            pending.delete(id);
            const body = src.startsWith('data:')
              ? fetch(src).then((response) => response.blob())
              : Promise.resolve({ url: src });
            adopt(view, host(), id, body);
          } else if (blob && !shows(outerOf(view).state, image, blob)) {
            link(host(), { blob }).catch(host().fail);
          }
        });
        return slice;
      },
      handlePaste(view, event) {
        const files = imageFiles(event.clipboardData?.files);
        if (!files.length || event.clipboardData?.getData('text/plain').trim()) return false;
        insertImages(view, host(), files);
        return true;
      },
      handleDrop(view, event, _slice, moved) {
        const files = imageFiles(event.dataTransfer?.files);
        if (moved || !files.length) return false;
        const at = view.posAtCoords({ left: event.clientX, top: event.clientY });
        insertImages(view, host(), files, at?.pos ?? view.state.doc.content.size);
        return true;
      },
    },
  });
}

export function selectedImage(state: EditorState): { node: Node; pos: number } | null {
  const { selection } = state;
  return selection instanceof NodeSelection && selection.node.type === image
    ? { node: selection.node, pos: selection.from }
    : null;
}

/** A handle at the frame's corner that resizes it as a share of the block's column, which the
 * block's width keeps once the drag ends. */
export function resizeHandle(
  view: EditorView,
  getPos: () => number | undefined,
  align: () => unknown,
  dom: HTMLElement,
  frame: HTMLElement,
): HTMLElement {
  const handle = document.createElement('span');
  handle.className = 'ponistra-resize';
  handle.addEventListener('pointerdown', (event) => {
    if (!view.editable) return;
    event.preventDefault();
    const column = dom.getBoundingClientRect().width;
    const start = event.clientX;
    const width = frame.getBoundingClientRect().width;
    const pull = align() === 'center' ? 2 : align() === 'right' ? -1 : 1;
    let share = (width / column) * 100;
    handle.setPointerCapture(event.pointerId);
    const move = (moved: PointerEvent) => {
      share = Math.min(100, Math.max(5, ((width + (moved.clientX - start) * pull) / column) * 100));
      frame.style.width = `${share}%`;
    };
    const done = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', done);
      handle.removeEventListener('pointercancel', done);
      const pos = getPos();
      if (pos !== undefined) {
        view.dispatch(view.state.tr.setNodeAttribute(pos, 'width', widthOf(share)));
      }
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', done);
    handle.addEventListener('pointercancel', done);
  });
  frame.append(handle);
  return handle;
}

/** An image in the editor: a frame its corner handle resizes, as a share of the column. */
export class ImageView implements NodeView {
  dom: HTMLElement;
  private handle: HTMLElement | null = null;

  constructor(
    private node: Node,
    view: EditorView,
    getPos: () => number | undefined,
    waiting: string,
  ) {
    this.dom = DOMSerializer.renderSpec(document, imageSpec(node)).dom as HTMLElement;
    const img = this.dom.querySelector('img');
    if (!img) {
      this.dom.dataset.waiting = waiting;
      return;
    }
    const frame = document.createElement('span');
    frame.className = 'ponistra-frame';
    frame.style.width = img.style.width;
    img.removeAttribute('style');
    img.replaceWith(frame);
    frame.append(img);
    this.handle = resizeHandle(view, getPos, () => this.node.attrs.align, this.dom, frame);
  }

  update(node: Node): boolean {
    if (!node.sameMarkup(this.node)) return false;
    this.node = node;
    return true;
  }

  stopEvent(event: Event): boolean {
    return event.target === this.handle;
  }

  ignoreMutation(): boolean {
    return true;
  }
}

/** Right-clicking an image or a PDF selects it, so its menu acts on it. */
export function selectFigureAt(view: EditorView, target: EventTarget | null): void {
  const figure =
    target instanceof Element ? target.closest('figure[data-image], figure[data-pdf]') : null;
  if (!figure || !view.dom.contains(figure)) return;
  const pos = view.posAtDOM(figure, 0);
  const type = view.state.doc.nodeAt(pos)?.type;
  if (type !== image && type !== schema.nodes.pdf) return;
  view.dispatch(view.state.tr.setSelection(NodeSelection.create(view.state.doc, pos)));
}
