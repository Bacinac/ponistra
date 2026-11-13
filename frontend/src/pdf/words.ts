import type { MessageKey } from '../i18n/hr';

const ID = 'data-l10n-id';
const ARGS = 'data-l10n-args';

type Args = Record<string, unknown>;

interface Said {
  text?: string;
  attributes?: Record<string, string>;
}

interface Say {
  t: (key: MessageKey) => string;
  formatDate: (iso: string) => string;
  formatNumber: (value: number) => string;
}

function messages({ t, formatDate, formatNumber }: Say): Record<string, (args: Args) => Said> {
  return {
    'pdfjs-page-landmark': ({ page }) => ({
      attributes: {
        'aria-label': `${t('pdf.page')} ${typeof page === 'number' ? formatNumber(page) : page}`,
      },
    }),
    'pdfjs-text-annotation-type': () => ({ attributes: { alt: t('pdf.annotation') } }),
    'pdfjs-annotation-date-time-string': ({ dateObj }) => ({
      text: formatDate(new Date(dateObj as number).toISOString()),
    }),
    'pdfjs-show-comment-button': () => ({ attributes: { title: t('pdf.comment') } }),
  };
}

/** The words pdf.js puts on the pages it draws, in the interface's language: it marks each element
 * with a message id and arguments, and this fills them in as the elements appear. An id without a
 * message is reported rather than left in English. */
export class Words {
  readonly #language: string;
  readonly #messages: Record<string, (args: Args) => Said>;
  readonly #roots = new Set<Element>();
  readonly #observer = new MutationObserver((records) => this.#changed(records));

  constructor(language: string, say: Say) {
    this.#language = language;
    this.#messages = messages(say);
  }

  getLanguage() {
    return this.#language;
  }

  getDirection() {
    return 'ltr';
  }

  async get(ids: string | string[], args: Args | null = null) {
    if (Array.isArray(ids)) return ids.map((id) => this.#said(id, {})?.text);
    return this.#said(ids, args ?? {})?.text;
  }

  async translate(element: Element) {
    this.#roots.add(element);
    this.#observe(element);
    this.#within(element);
  }

  async translateOnce(element: Element) {
    this.#apply(element);
  }

  async destroy() {
    this.#observer.disconnect();
    this.#roots.clear();
  }

  pause() {
    this.#changed(this.#observer.takeRecords());
    this.#observer.disconnect();
  }

  resume() {
    for (const root of this.#roots) this.#observe(root);
  }

  #observe(root: Element) {
    this.#observer.observe(root, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: [ID, ARGS],
    });
  }

  #changed(records: MutationRecord[]) {
    for (const record of records) {
      if (record.type === 'attributes') this.#apply(record.target as Element);
      for (const node of record.addedNodes) {
        if (node instanceof Element) this.#within(node);
      }
    }
  }

  #within(element: Element) {
    if (element.hasAttribute(ID)) this.#apply(element);
    for (const marked of element.querySelectorAll(`[${ID}]`)) this.#apply(marked);
  }

  #apply(element: Element) {
    const id = element.getAttribute(ID);
    if (!id) return;
    const said = this.#said(id, JSON.parse(element.getAttribute(ARGS) ?? '{}'));
    if (!said) return;
    if (said.text !== undefined && element.textContent !== said.text) {
      element.textContent = said.text;
    }
    for (const [name, value] of Object.entries(said.attributes ?? {})) {
      if (element.getAttribute(name) !== value) element.setAttribute(name, value);
    }
  }

  #said(id: string, args: Args): Said | null {
    const message = this.#messages[id];
    if (message) return message(args);
    console.error(`pdf.js asked for the words "${id}", which PONISTRA does not have`);
    return null;
  }
}
