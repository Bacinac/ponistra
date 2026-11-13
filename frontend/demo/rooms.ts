import * as decoding from 'lib0/decoding';
import * as encoding from 'lib0/encoding';
import * as awarenessProtocol from 'y-protocols/awareness';
import * as syncProtocol from 'y-protocols/sync';
import * as Y from 'yjs';
import { missing, recordedFile } from './recording';
import type { DemoSocket, Peer } from './sockets';

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;
const MESSAGE_QUERY_AWARENESS = 3;

interface Room {
  doc: Y.Doc;
  awareness: awarenessProtocol.Awareness;
  sockets: Set<DemoSocket>;
}

/** The rooms of the tab, kept while it is open: what the visitor wrote in a document is there
 * when they come back to it. */
const rooms = new Map<string, Promise<Room | null>>();
/** Rooms of what the visitor made in the tab, by the state each starts from as the backend's
 * would: none for a tab, the styles of a new document for its own room. */
export const madeRooms = new Map<string, Uint8Array | null>();

async function opened(name: string): Promise<Room | null> {
  const doc = new Y.Doc();
  const made = madeRooms.get(name);
  if (made) Y.applyUpdate(doc, made);
  else if (made === undefined) {
    const file = await recordedFile(`collab/${name}.bin`);
    if (!file) {
      missing(`collab ${name}`);
      return null;
    }
    Y.applyUpdate(doc, new Uint8Array(await file.arrayBuffer()));
  }
  const room: Room = { doc, awareness: new awarenessProtocol.Awareness(doc), sockets: new Set() };
  // The server takes no part in presence.
  room.awareness.setLocalState(null);
  doc.on('update', (update: Uint8Array, origin: unknown) => {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    const message = encoding.toUint8Array(encoder);
    for (const socket of room.sockets) if (socket !== origin) socket.deliver(message);
  });
  room.awareness.on(
    'update',
    ({ added, updated, removed }: Record<string, number[]>, origin: unknown) => {
      const changed = [...added, ...updated, ...removed];
      const encoder = encoding.createEncoder();
      encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
      encoding.writeVarUint8Array(
        encoder,
        awarenessProtocol.encodeAwarenessUpdate(room.awareness, changed),
      );
      const message = encoding.toUint8Array(encoder);
      for (const socket of room.sockets) if (socket !== origin) socket.deliver(message);
    },
  );
  return room;
}

function bytesOf(data: string | ArrayBufferLike | Blob | ArrayBufferView): Uint8Array | null {
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  if (ArrayBuffer.isView(data))
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  return null;
}

/** A document's room as the backend's collaboration server keeps it (apps/collab/server.py),
 * from the state the walk recorded. */
export function joinRoom(name: string, socket: DemoSocket): Peer {
  let room: Room | null = null;
  const waiting: Uint8Array[] = [];
  let left = false;

  const take = (message: Uint8Array) => {
    const decoder = decoding.createDecoder(message);
    const encoder = encoding.createEncoder();
    const type = decoding.readVarUint(decoder);
    if (type === MESSAGE_SYNC) {
      encoding.writeVarUint(encoder, MESSAGE_SYNC);
      syncProtocol.readSyncMessage(decoder, encoder, room!.doc, socket);
      if (encoding.length(encoder) > 1) socket.deliver(encoding.toUint8Array(encoder));
    } else if (type === MESSAGE_AWARENESS) {
      awarenessProtocol.applyAwarenessUpdate(
        room!.awareness,
        decoding.readVarUint8Array(decoder),
        socket,
      );
    } else if (type === MESSAGE_QUERY_AWARENESS) {
      encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
      encoding.writeVarUint8Array(
        encoder,
        awarenessProtocol.encodeAwarenessUpdate(room!.awareness, [
          ...room!.awareness.getStates().keys(),
        ]),
      );
      socket.deliver(encoding.toUint8Array(encoder));
    }
  };

  if (!rooms.has(name)) rooms.set(name, opened(name));
  void rooms.get(name)!.then((found) => {
    if (left) return;
    if (!found) {
      rooms.delete(name);
      // As the backend refuses a room it does not have.
      socket.close(4404, 'demo');
      return;
    }
    room = found;
    room.sockets.add(socket);
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeSyncStep1(encoder, room.doc);
    socket.deliver(encoding.toUint8Array(encoder));
    for (const message of waiting.splice(0)) take(message);
  });

  return {
    take: (data) => {
      const message = bytesOf(data);
      if (!message) return;
      if (room) take(message);
      else waiting.push(message.slice());
    },
    left: () => {
      left = true;
      if (!room) return;
      room.sockets.delete(socket);
      const clients = [...room.awareness.getStates().keys()].filter(
        (client) => client !== room!.doc.clientID,
      );
      if (room.sockets.size === 0) {
        awarenessProtocol.removeAwarenessStates(room.awareness, clients, null);
      }
    },
  };
}
