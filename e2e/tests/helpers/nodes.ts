import type { Page } from '@playwright/test';

// frontend/src/address.ts and nodeHref in tree.tsx: the built app keeps its modules to itself.
const DIGITS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
const ROUTES: Record<string, string> = { folder: 'f', document: 'd', file: 'p' };

/** Where a folder, document or file opens. */
export function nodeHref(node: { id: string; kind: string; title: string }): string {
  if (!(node.kind in ROUTES)) throw new Error(`no address for a node of kind ${node.kind}`);
  let value = BigInt(`0x${node.id.replaceAll('-', '')}`);
  let digits = '';
  for (let place = 0; place < 22; place++) {
    digits = DIGITS[Number(value % 62n)] + digits;
    value /= 62n;
  }
  const words = node.title
    .toLowerCase()
    .replaceAll('đ', 'dj')
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 60)
    .replace(/^-+|-+$/g, '');
  return `/${ROUTES[node.kind]}/${words ? `${words}-${digits}` : digits}`;
}

/** The id a part of an address ends in. */
export function idIn(segment: string): string {
  let value = 0n;
  for (const digit of segment.slice(-22)) value = value * 62n + BigInt(DIGITS.indexOf(digit));
  const hex = value.toString(16).padStart(32, '0');
  return [20, 16, 12, 8].reduce((uuid, at) => `${uuid.slice(0, at)}-${uuid.slice(at)}`, hex);
}

/** A new document in the root, by the address the app itself gives it. */
export async function newDocument(page: Page, title: string): Promise<string> {
  await page.goto('/');
  const made = await page.evaluate(async (title) => {
    await fetch('/api/auth/session');
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const response = await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ kind: 'document', title, parent: null }),
    });
    if (!response.ok) throw new Error(`POST /api/nodes: ${response.status}`);
    return response.json();
  }, title);
  return nodeHref(made);
}

/** A board of `html` in the root, filed in `group` when one is given, by its node's id. */
export async function newBoard(
  page: Page,
  title: string,
  html: string,
  group?: string,
): Promise<string> {
  return page.evaluate(
    async ({ title, html, group }) => {
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
      const json = { 'Content-Type': 'application/json', 'X-CSRFToken': token };
      const data = new TextEncoder().encode(html);
      const begun = await fetch('/api/uploads', {
        method: 'POST',
        headers: json,
        body: JSON.stringify({ size: data.length }),
      });
      let upload = await begun.json();
      while (upload.blob === null) {
        const sent = await fetch(`/api/uploads/${upload.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/octet-stream',
            'X-CSRFToken': token,
            'Upload-Offset': String(upload.received),
          },
          body: data.slice(upload.received, upload.received + upload.chunk),
        });
        upload = await sent.json();
      }
      const made = await fetch('/api/nodes', {
        method: 'POST',
        headers: json,
        body: JSON.stringify({
          kind: 'file',
          title,
          blob: upload.blob.sha256,
          extension: 'html',
        }),
      });
      if (!made.ok) throw new Error(`POST /api/nodes: ${made.status}`);
      const { id } = (await made.json()) as { id: string };
      if (!group) return id;
      const filed = await fetch('/api/nodes/boards', {
        method: 'POST',
        headers: json,
        body: JSON.stringify({ node: id, group }),
      });
      if (!filed.ok) throw new Error(`POST /api/nodes/boards: ${filed.status}`);
      return id;
    },
    { title, html, group },
  );
}

/** New tabs at the end of the document at `address`. */
export async function addTabs(page: Page, address: string, titles: string[]): Promise<void> {
  await page.evaluate(
    async ({ id, titles }) => {
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
      for (const title of titles) {
        const response = await fetch(`/api/nodes/${id}/tabs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
          body: JSON.stringify({ title }),
        });
        if (!response.ok) throw new Error(`POST tabs: ${response.status}`);
      }
    },
    { id: idIn(address.split('/')[2]), titles },
  );
}
