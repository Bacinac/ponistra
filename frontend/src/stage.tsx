import { Folder, LayoutDashboard } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { RoomEvent, type Room } from 'livekit-client';
import { csrfToken, deleteJson, postJson } from './api';
import { useI18n } from './i18n';
import { useChanges } from './live';
import { MenuItem, MenuSub } from './menu';
import { boardGroups, useBoards } from './tree';

/** A board a member shows everyone in the meeting, as the server told the room. */
export interface Staged {
  id: string;
  title: string;
  by: string | null;
  user: number | null;
  page: string;
  data: string;
}

export function useStaged(room: Room): Staged | null {
  const read = useCallback((): Staged | null => {
    try {
      return (JSON.parse(room.metadata || '{}') as { board?: Staged | null }).board ?? null;
    } catch {
      return null;
    }
  }, [room]);
  const [staged, setStaged] = useState(read);
  useEffect(() => {
    const changed = () => setStaged(read());
    room.on(RoomEvent.RoomMetadataChanged, changed);
    changed();
    return () => void room.off(RoomEvent.RoomMetadataChanged, changed);
  }, [room, read]);
  return staged;
}

/** The board on the stage, drawn in this browser from the board itself: a new page draws it
 * again, and what it keeps changing tells the page to read it again. */
export function StagedBoard({
  meeting,
  guestKey,
  board,
}: {
  meeting: string;
  guestKey?: string | null;
  board: Staged;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    frame.current?.contentWindow?.postMessage({ ponistra: 'changed' }, window.location.origin);
  }, [board.data]);
  const base = guestKey
    ? `/api/meetings/${meeting}/guests/${guestKey}/stage`
    : `/api/meetings/${meeting}/stage`;
  return (
    <iframe
      ref={frame}
      key={`${board.id}:${board.page}`}
      src={base}
      title={board.title}
      className="h-full w-full border-0 bg-surface"
    />
  );
}

export function showBoard(meeting: string, board: string): Promise<unknown> {
  return postJson(`/api/meetings/${meeting}/board`, { board });
}

function takenDown(meeting: string, keepalive = false): Promise<Response> {
  return fetch(`/api/meetings/${meeting}/board`, {
    method: 'DELETE',
    keepalive,
    headers: { 'X-CSRFToken': csrfToken() },
  });
}

export function hideBoard(meeting: string): Promise<void> {
  return deleteJson(`/api/meetings/${meeting}/board`);
}

/** For the member who shows a board: everyone draws it again as it changes, and it leaves the
 * stage when they leave the call, closing the page included. */
export function useShowing(meeting: string, mine: boolean) {
  const held = useRef(mine);
  held.current = mine;
  useEffect(() => {
    const leave = () => {
      if (held.current) void takenDown(meeting, true);
    };
    window.addEventListener('pagehide', leave);
    return () => {
      window.removeEventListener('pagehide', leave);
      leave();
    };
  }, [meeting]);
}

export function BoardChanges({ meeting }: { meeting: string }) {
  const told = useCallback(
    (areas: string[]) => {
      if (areas.some((area) => area === 'boards' || area === 'nodes' || area === '*'))
        postJson(`/api/meetings/${meeting}/board/changed`).catch((error: unknown) =>
          console.error('telling the board changed failed', error),
        );
    },
    [meeting],
  );
  useChanges(told);
  return null;
}

/** The user's boards by group, each shown on the stage once chosen. */
export function BoardChoices({
  disabled,
  onBoard,
}: {
  disabled: boolean;
  onBoard: (board: string) => void;
}) {
  const { t } = useI18n();
  return (
    <MenuSub icon={LayoutDashboard} label={t('meeting.shareBoard')} disabled={disabled}>
      <Boards onBoard={onBoard} />
    </MenuSub>
  );
}

function Boards({ onBoard }: { onBoard: (board: string) => void }) {
  const { t } = useI18n();
  const boards = useBoards();
  if (!boards.data)
    return (
      <MenuItem icon={LayoutDashboard} label={t('tree.loading')} disabled onSelect={() => {}} />
    );
  const groups = boardGroups(boards.data.children, t);
  if (!groups.length)
    return (
      <MenuItem icon={LayoutDashboard} label={t('meeting.noBoards')} disabled onSelect={() => {}} />
    );
  return (
    <>
      {groups.map((group) => (
        <MenuSub key={group.key} icon={Folder} label={group.title}>
          {group.boards.map((board) => (
            <MenuItem
              key={board.id}
              icon={LayoutDashboard}
              label={board.title}
              onSelect={() => onBoard(board.id)}
            />
          ))}
        </MenuSub>
      ))}
    </>
  );
}
