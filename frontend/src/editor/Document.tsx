import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import * as Y from 'yjs';
import { threadsKey } from '../comments';
import { Loading } from '../frame';
import { useI18n } from '../i18n';
import type { Found, OutlineStore } from '../tabs';
import { nodeKey, type DocumentLocale, type LiveTab, type TreeNode } from '../tree';
import { joinRoom, useKept, useRecheck } from '../room';
import { LiveEditor } from './Editor';
import { GridClient } from './grids';
import { watchNews } from './news';
import { shortId } from './blocks';
import { PageDialog, type SectionPages } from './PageDialog';
import { Show } from './Show';
import type { From } from './show';
import { StylesDialog } from './StylesDialog';

/** The document's own state once its room has synced, so no block shows unstyled first. The room
 * also tells when the document's comments or tabs change. */
function useOwnRoom(room: string, documentId: string): { doc: Y.Doc | null; lost: boolean } {
  const recheck = useRecheck(documentId);
  const keep = useKept(documentId);
  const queryClient = useQueryClient();
  const [doc, setDoc] = useState<Y.Doc | null>(null);
  const [lost, setLost] = useState(false);
  useEffect(() => {
    const own = new Y.Doc();
    const { provider, leave, onReady } = joinRoom(room, own, recheck, keep);
    provider.on('status', (event) => setLost(event.status === 'disconnected'));
    onReady((ready) => ready && setDoc(own));
    watchNews(provider, 'comments', () =>
      queryClient.invalidateQueries({ queryKey: threadsKey(documentId) }),
    );
    watchNews(provider, 'tabs', () =>
      queryClient.invalidateQueries({ queryKey: nodeKey(documentId) }),
    );
    return () => {
      leave();
      own.destroy();
    };
  }, [room, recheck, keep, queryClient, documentId]);
  return { doc, lost };
}

/** The document's grids over one socket while it is open, whichever of its tabs shows. */
function useGrids(documentId: string): GridClient | null {
  const [grids, setGrids] = useState<GridClient | null>(null);
  useEffect(() => {
    const client = new GridClient(documentId);
    client.watch(null);
    setGrids(client);
    return () => {
      setGrids(null);
      client.close();
    };
  }, [documentId]);
  return grids;
}

export default function DocumentEditor({
  room,
  tab,
  tabs,
  documentId,
  original,
  home,
  readOnly,
  found,
  outline,
  locale,
  title,
  dialog,
  onDialogClose,
  requested,
  onRequested,
}: {
  room: string;
  tab: Pick<LiveTab, 'id' | 'room'> | null;
  tabs: readonly Pick<LiveTab, 'id' | 'title'>[];
  documentId: string;
  original: TreeNode['original'];
  /** The document's address, under which each tab has its own. */
  home: string;
  readOnly: boolean;
  found: Found | null;
  outline: OutlineStore;
  locale: DocumentLocale;
  title: string;
  dialog: 'styling' | 'page' | null;
  onDialogClose: () => void;
  /** A command or a backend's action asked for outside the editor, which the tab's editor runs. */
  requested: string | null;
  onRequested: () => void;
}) {
  const { t } = useI18n();
  const { doc, lost } = useOwnRoom(room, documentId);
  const grids = useGrids(documentId);
  const [show, setShow] = useState<{ id: string; from: From } | null>(null);
  const [section, setSection] = useState<SectionPages | null>(null);
  if (!doc || !grids) {
    return lost ? <p className="text-danger">{t('collab.disconnected')}</p> : <Loading />;
  }
  return (
    <>
      {tab && (
        <LiveEditor
          key={tab.room}
          own={doc}
          grids={grids}
          room={tab.room}
          documentId={documentId}
          original={original}
          tab={tab.id}
          home={home}
          tabs={tabs}
          readOnly={readOnly}
          found={found}
          outline={outline}
          locale={locale}
          title={title}
          requested={requested}
          onRequested={onRequested}
          onSection={setSection}
          onPresent={(from) => setShow({ id: shortId(), from })}
        />
      )}
      {show && (
        <Show
          nodeId={documentId}
          show={show.id}
          from={show.from}
          locale={locale}
          onEnd={() => setShow(null)}
        />
      )}
      {dialog === 'styling' && (
        <StylesDialog doc={doc} documentId={documentId} onClose={onDialogClose} />
      )}
      {dialog === 'page' && (
        <PageDialog
          own={doc}
          tab={tab?.id ?? null}
          section={section}
          first={tabs[0]?.id === tab?.id}
          several={tabs.length > 1}
          onClose={onDialogClose}
        />
      )}
    </>
  );
}
