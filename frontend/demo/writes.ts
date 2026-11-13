import { madeBooks } from './grids';
import { recordedFile } from './recording';
import { madeRooms } from './rooms';
import { declined, type Asked, type Given, type Server } from './server';

/** A write the demo carries out in the tab, changing the recorded reads it shows in. */
export interface Write {
  method: string;
  path: RegExp;
  run: (server: Server, asked: Asked, match: RegExpExecArray) => Given | Promise<Given>;
}

/** Ids of what the visitor makes, past any the recording holds. */
let lastId = 1_000_000;
export function newId(): number {
  return ++lastId;
}

function nowIso(): string {
  return new Date().toISOString();
}

type Fields = Record<string, unknown>;

interface Task {
  id: number;
  text: string;
  due: string | null;
  done: boolean;
  done_at: string | null;
  source: unknown;
  changed_at: string;
}

const TASKS = 'GET /api/tasks';

function tasks(server: Server): Task[] {
  const listed = server.read<{ tasks: Task[] }>(TASKS);
  if (listed) return listed.tasks;
  const made = { tasks: [] as Task[] };
  server.write(TASKS, made);
  return made.tasks;
}

function filledTask(task: Task, given: Fields): Given | null {
  if ('text' in given) {
    task.text = String(given.text ?? '')
      .split(/\s+/)
      .filter(Boolean)
      .join(' ')
      .slice(0, 1000);
    if (!task.text) return { status: 400, body: { error: 'text_required' } };
  }
  if ('due' in given) task.due = (given.due as string | null) || null;
  if ('done' in given) {
    task.done = Boolean(given.done);
    task.done_at = task.done ? (task.done_at ?? nowIso()) : null;
  }
  if ('source' in given) task.source = given.source ?? null;
  task.changed_at = nowIso();
  return null;
}

function taskWrites(): Write[] {
  return [
    {
      method: 'POST',
      path: /^\/api\/tasks$/,
      run: (server, { body }) => {
        const task: Task = {
          id: newId(),
          text: '',
          due: null,
          done: false,
          done_at: null,
          source: null,
          changed_at: nowIso(),
        };
        const refused = filledTask(task, { text: '', ...(body as Fields) });
        if (refused) return refused;
        tasks(server).push(task);
        server.write(`GET /api/tasks/${task.id}`, task);
        server.tell(['tasks']);
        return { status: 201, body: task };
      },
    },
    {
      method: 'PATCH',
      path: /^\/api\/tasks\/(\d+)$/,
      run: (server, { body }, [, id]) => {
        const task = tasks(server).find((each) => each.id === Number(id));
        if (!task) return { status: 404, body: { error: 'not_found' } };
        const refused = filledTask(task, body as Fields);
        if (refused) return refused;
        server.tell(['tasks']);
        return { status: 200, body: task };
      },
    },
    {
      method: 'DELETE',
      path: /^\/api\/tasks\/(\d+)$/,
      run: (server, _, [, id]) => {
        const listed = tasks(server);
        const at = listed.findIndex((each) => each.id === Number(id));
        if (at < 0) return { status: 404, body: { error: 'not_found' } };
        listed.splice(at, 1);
        server.tell(['tasks']);
        return { status: 204 };
      },
    },
  ];
}

const SESSION = 'GET /api/auth/session';

/** The language and themes the visitor picks hold for the tab, as the account would keep them. */
function preferenceWrites(): Write[] {
  return [
    {
      method: 'PATCH',
      path: /^\/api\/auth\/preferences$/,
      run: (server, { body }) => {
        const session = server.read<{ user: Fields | null }>(SESSION);
        if (!session?.user) return { status: 401, body: { error: 'not_signed_in' } };
        Object.assign(session.user, body as Fields);
        return { status: 200, body: session };
      },
    },
  ];
}

function me(server: Server): { id: number; name: string } {
  const user = server.read<{ user: { id: number; name: string } | null }>(SESSION)?.user;
  if (!user) throw new Error('The recording has no one signed in');
  return user;
}

interface Message {
  id: number;
  text: string;
  at: string;
  edited: boolean;
  thread: { replies: number; unread: number };
}

interface Summary {
  id: string;
  unread: number;
  mentions: number;
  threads: number;
  changed: string;
  last: unknown;
}

/** The pages of a conversation's messages, the latest first. */
function pagesOf(server: Server, id: string): Message[][] {
  const pattern = new RegExp(`^GET /api/conversations/${id}/messages(\\?|$)`);
  return [...server.reads<{ messages: Message[] }>(pattern)].map(([, page]) => page.messages);
}

function liveSummary(server: Server, id: string): Summary | undefined {
  const conversations = server.live?.conversations as Summary[] | undefined;
  return conversations?.find((each) => each.id === id);
}

/** Messages written in a conversation, which the backend keeps (apps/chat/views.py). */
function chatWrites(): Write[] {
  return [
    {
      method: 'POST',
      path: /^\/api\/conversations\/([^/]+)\/messages$/,
      run: (server, { body }, [, id]) => {
        const given = body as {
          body: string;
          everyone?: boolean;
          parent?: number;
          attachments?: unknown[];
        };
        if (given.attachments?.length) return declined(`POST /api/conversations/${id}/messages`);
        const message = {
          id: newId(),
          by: me(server).name,
          guest: false,
          mine: true,
          text: given.body,
          at: nowIso(),
          edited: false,
          reactions: [],
          mentions: [],
          everyone: Boolean(given.everyone),
          thread: { replies: 0, unread: 0 },
          meeting: null,
          kept: null,
          files: [],
          items: [],
        };
        const parent = given.parent === undefined ? undefined : String(given.parent);
        // The latest page alone, the one asked without `before`.
        const key = `GET /api/conversations/${id}/messages${parent ? `/${parent}/replies` : ''}`;
        if (!server.read(key)) server.write(key, { messages: [], more: false });
        server.read<{ messages: Message[] }>(key)!.messages.push(message);
        if (parent) {
          for (const page of pagesOf(server, id)) {
            const root = page.find((each) => String(each.id) === parent);
            if (root) root.thread = { ...root.thread, replies: root.thread.replies + 1 };
          }
        } else {
          const summary = liveSummary(server, id);
          if (summary) {
            summary.last = {
              id: message.id,
              by: message.by,
              text: message.text,
              at: message.at,
              files: 0,
              meeting: false,
            };
            summary.changed = message.at;
            const conversations = server.live!.conversations as Summary[];
            conversations.splice(conversations.indexOf(summary), 1);
            conversations.unshift(summary);
          }
        }
        server.tell(['conversations'], true);
        return { status: 201, body: message };
      },
    },
    {
      method: 'PATCH',
      path: /^\/api\/conversations\/([^/]+)\/messages\/(\d+)$/,
      run: (server, { body }, [, id, mid]) => {
        const text = (body as { body: string }).body;
        let found: Message | undefined;
        for (const page of [...pagesOf(server, id), ...repliesOf(server, id)]) {
          const message = page.find((each) => each.id === Number(mid));
          if (message) Object.assign((found = message), { text, edited: true });
        }
        if (!found) return { status: 404, body: { error: 'no_message' } };
        server.tell(['conversations']);
        return { status: 200, body: found };
      },
    },
    {
      method: 'DELETE',
      path: /^\/api\/conversations\/([^/]+)\/messages\/(\d+)$/,
      run: (server, _, [, id, mid]) => {
        for (const page of [...pagesOf(server, id), ...repliesOf(server, id)]) {
          const at = page.findIndex((each) => each.id === Number(mid));
          if (at >= 0) page.splice(at, 1);
        }
        server.tell(['conversations']);
        return { status: 204 };
      },
    },
    {
      // Reading a conversation, as the page does on its own whenever it shows one.
      method: 'POST',
      path: /^\/api\/conversations\/([^/]+)(?:\/messages\/\d+)?\/read$/,
      run: (server, _, [, id]) => {
        const summary = liveSummary(server, id);
        if (summary && (summary.unread || summary.mentions || summary.threads)) {
          Object.assign(summary, { unread: 0, mentions: 0, threads: 0 });
          server.tell(['conversations'], true);
        }
        return { status: 204 };
      },
    },
  ];
}

function repliesOf(server: Server, id: string): Message[][] {
  const pattern = new RegExp(`^GET /api/conversations/${id}/messages/\\d+/replies(\\?|$)`);
  return [...server.reads<{ messages: Message[] }>(pattern)].map(([, page]) => page.messages);
}

interface Unsent {
  id: number;
  updated_at: string;
  send_at: string | null;
}

const UNSENT = 'GET /api/mail/unsent';

function unsentOf(server: Server): Unsent[] {
  if (!server.read(UNSENT)) server.write(UNSENT, { unsent: [] });
  return server.read<{ unsent: Unsent[] }>(UNSENT)!.unsent;
}

const LATER = 'GET /api/mail/later';

function unsentMade(server: Server, given: Fields, sendAt: string | null = null): Unsent {
  const unsent = {
    account: null,
    sending: false,
    failed: '',
    to: [],
    cc: [],
    bcc: [],
    subject: '',
    html: '',
    files: [],
    ...given,
    id: newId(),
    updated_at: nowIso(),
    send_at: sendAt,
  };
  if (sendAt === null) unsentOf(server).unshift(unsent);
  else {
    if (!server.read(LATER)) server.write(LATER, { later: [] });
    server.read<{ later: Unsent[] }>(LATER)!.later.push(unsent);
  }
  return unsent;
}

function unsentGone(server: Server, id: unknown): void {
  const listed = unsentOf(server);
  const at = listed.findIndex((each) => each.id === Number(id));
  if (at >= 0) listed.splice(at, 1);
}

/** Mail written and sent from the tab: kept while it is written, as the backend keeps it
 * (apps/mail), and gone once sent; what it carries attached needs the server to upload. */
function mailWrites(): Write[] {
  const attached = (body: unknown) => ((body as { files?: unknown[] }).files ?? []).length > 0;
  return [
    {
      method: 'POST',
      path: /^\/api\/mail\/unsent$/,
      run: (server, { body }) => {
        const unsent = unsentMade(server, body as Fields);
        server.tell(['mail']);
        return { status: 201, body: unsent };
      },
    },
    {
      method: 'PUT',
      path: /^\/api\/mail\/unsent\/(\d+)$/,
      run: (server, { body }, [, id]) => {
        const unsent = unsentOf(server).find((each) => each.id === Number(id));
        if (!unsent) return { status: 404, body: { error: 'not_found' } };
        Object.assign(unsent, body as Fields, { id: unsent.id, updated_at: nowIso() });
        server.tell(['mail']);
        return { status: 200, body: unsent };
      },
    },
    {
      method: 'DELETE',
      path: /^\/api\/mail\/unsent\/(\d+)$/,
      run: (server, _, [, id]) => {
        unsentGone(server, id);
        server.tell(['mail']);
        return { status: 204 };
      },
    },
    {
      method: 'POST',
      path: /^\/api\/mail\/send$/,
      run: (server, { key, body }) => {
        if (attached(body)) return declined(key);
        unsentGone(server, (body as Fields).unsent);
        server.tell(['mail']);
        return { status: 200, body: { refused: [], kept: true } };
      },
    },
    {
      method: 'POST',
      path: /^\/api\/mail\/later$/,
      run: (server, { key, body }) => {
        if (attached(body)) return declined(key);
        const { at, unsent, ...given } = body as Fields;
        unsentGone(server, unsent);
        const later = unsentMade(server, given, at as string);
        server.tell(['mail']);
        return { status: 201, body: later };
      },
    },
  ];
}

type Flags = Partial<Record<'seen' | 'flagged', boolean>>;

/** Every message the recorded reads of mail show, each listing its own copy. */
function* mailMessages(server: Server): Generator<Fields & { id: number; seen: boolean }> {
  const walk = function* (value: unknown): Generator<Fields & { id: number; seen: boolean }> {
    if (Array.isArray(value)) for (const each of value) yield* walk(each);
    else if (value && typeof value === 'object') {
      const fields = value as Fields;
      if (typeof fields.id === 'number' && typeof fields.seen === 'boolean') {
        yield fields as Fields & { id: number; seen: boolean };
      }
      for (const each of Object.values(fields)) yield* walk(each);
    }
  };
  for (const [, body] of server.reads(/^GET \/api\/mail\//)) yield* walk(body);
}

/** Marks the messages read, unread, flagged or not, wherever they are shown. */
type Shown = Fields & { id: number; seen: boolean };

function marked(server: Server, chosen: (message: Shown) => boolean, flags: Flags): number {
  const changed = new Set<number>();
  for (const message of mailMessages(server)) {
    if (!chosen(message)) continue;
    for (const [flag, value] of Object.entries(flags) as [keyof Flags, boolean][]) {
      if (flag in message && message[flag] !== value) {
        message[flag] = value;
        changed.add(message.id);
      }
    }
  }
  return changed.size;
}

const MARKS: Record<string, Flags> = {
  seen: { seen: true },
  unseen: { seen: false },
  flagged: { flagged: true },
  unflagged: { flagged: false },
};

/** Reading and flagging mail, which the page does on its own as a message opens; moving it
 * between folders needs the server. */
function mailMarkWrites(): Write[] {
  return [
    {
      method: 'PATCH',
      path: /^\/api\/mail\/messages\/(\d+)$/,
      run: (server, { key, body }, [, id]) => {
        const flags = body as Flags;
        if (Object.keys(flags).some((flag) => !(flag in MARKS.seen || flag in MARKS.flagged))) {
          return declined(key);
        }
        marked(server, (message) => message.id === Number(id), flags);
        const shown = [...mailMessages(server)].find((message) => message.id === Number(id));
        server.tell(['mail']);
        return shown ? { status: 200, body: shown } : { status: 404, body: { error: 'not_found' } };
      },
    },
    {
      method: 'POST',
      path: /^\/api\/mail\/folders\/(?:\d+|flagged)\/chosen$/,
      run: (server, { key, body }) => {
        const { action, where = {} } = body as {
          action: string;
          where?: { messages?: number[]; seen?: boolean; account?: number };
        };
        const flags = MARKS[action];
        if (!flags) return declined(key);
        const ids = where.messages && new Set(where.messages);
        const changed = marked(
          server,
          (message) =>
            (!ids || ids.has(message.id)) &&
            (where.seen === undefined || message.seen === where.seen) &&
            (where.account === undefined ||
              !('account' in message) ||
              message.account === where.account),
          flags,
        );
        server.tell(['mail']);
        return { status: 200, body: { changed } };
      },
    },
  ];
}

interface Listing {
  folder: Fields | null;
  path: Fields[];
  root: string;
  role: string;
  confined: boolean;
  children: (Fields & { kind: string; title: string })[];
}

let template: Promise<Uint8Array | null> | null = null;

/** What the backend writes into a new document's own room (apps/documents/views.py `created`). */
function documentTemplate(): Promise<Uint8Array | null> {
  template ??= recordedFile('template.bin').then(
    async (file) => file && new Uint8Array(await file.arrayBuffer()),
  );
  return template;
}

function listingKey(parent: unknown): string {
  return parent ? `GET /api/nodes?parent=${String(parent)}` : 'GET /api/nodes';
}

/** Folders first, then by title, as the backend lists a folder. */
function placed(children: Listing['children'], child: Listing['children'][number]): void {
  children.push(child);
  children.sort(
    (a, b) =>
      Number(a.kind !== 'folder') - Number(b.kind !== 'folder') ||
      a.title.localeCompare(b.title, undefined, { sensitivity: 'base' }),
  );
}

/** A new document or folder in a folder the walk opened; a file or a link needs the server to
 * read it. */
function nodeWrites(): Write[] {
  return [
    {
      method: 'POST',
      path: /^\/api\/nodes$/,
      run: async (server, { key, body }) => {
        const given = body as { kind: string; title?: string; parent?: string | null };
        const listing = server.read<Listing>(listingKey(given.parent));
        if (!listing || (given.kind !== 'document' && given.kind !== 'folder')) {
          return declined(key);
        }
        const title = String(given.title ?? '').trim();
        if (!title) return { status: 400, body: { error: 'title_required' } };
        const styles = given.kind === 'document' ? await documentTemplate() : null;
        if (given.kind === 'document' && !styles) return declined(key);
        const { id: userId, name } = me(server);
        const email = server.read<{ user: { email: string } }>(SESSION)!.user.email;
        const by = { id: userId, email, name };
        const above = listing.path.at(-1);
        const node = {
          id: crypto.randomUUID(),
          parent: given.parent ?? null,
          kind: given.kind,
          title,
          locale: above?.locale ?? 'hr',
          updated_at: nowIso(),
          updated_by: by,
          size: null,
          holds: null,
          media_type: null,
          picture: null,
          extension: null,
          href: null,
          description: '',
          trashed_at: null,
          original: null,
          origin: null,
          macros: null,
          imported: null,
          company: false,
          confined: listing.confined,
          notes: false,
          links: false,
          boards: false,
          columns: null,
          agent_folder: null,
        };
        const placing = { root: listing.root, role: listing.role, confined: listing.confined };
        const path = [...listing.path, node];
        placed(listing.children, {
          ...node,
          audience: [{ kind: 'user', ...by, outside: false, role: 'own' }],
          role: listing.role,
          wider: false,
        });
        if (given.kind === 'folder') {
          server.write(listingKey(node.id), { folder: node, path, ...placing, children: [] });
        } else {
          const room = crypto.randomUUID();
          const tab = {
            id: crypto.randomUUID(),
            parent: null,
            title: '',
            position: 0,
            room: crypto.randomUUID(),
          };
          madeRooms.set(room, styles);
          madeRooms.set(tab.room, null);
          madeBooks.add(node.id);
          server.write(`GET /api/nodes/${node.id}`, {
            node,
            path,
            ...placing,
            room,
            tabs: [tab],
            pdf: null,
          });
          server.write(`GET /api/nodes/${node.id}/ai`, { consent: null });
          server.write(`GET /api/nodes/${node.id}/threads`, { threads: [] });
        }
        server.tell(['nodes']);
        return { status: 201, body: node };
      },
    },
  ];
}

/** A page that crashed says so in the browser's console; the demo has no log to report to. */
function crashWrites(): Write[] {
  return [{ method: 'POST', path: /^\/api\/crashes$/, run: () => ({ status: 204 }) }];
}

export const WRITES: Write[] = [
  ...taskWrites(),
  ...preferenceWrites(),
  ...chatWrites(),
  ...mailWrites(),
  ...mailMarkWrites(),
  ...nodeWrites(),
  ...crashWrites(),
];
