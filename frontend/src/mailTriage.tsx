import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { postJson } from './api';
import { Cancel, Modal } from './dialogs';
import { useI18n } from './i18n';
import { inBox, useBox } from './mailData';
import { primaryButton } from './styles';
import { errorMessage } from './tree';

/** How many messages triage sorts at once (`TRIAGED` in `acting.py`). */
export const TRIAGED = 50;

/** Where triage sends a message: one of the user's folders, or Archive or Junk before they exist. */
export type Destination = number | 'archive' | 'junk';

interface Proposal {
  message: number;
  to: Destination;
}

interface Sorted {
  id: number;
  subject: string;
  sender: { name?: string; address?: string };
}

/** Runs the registry's action on the messages (D14), in the mailbox shown. */
export function useMessageAction() {
  const queryClient = useQueryClient();
  const box = useBox();
  return useMutation({
    mutationFn: ({
      action,
      messages,
      parameters = {},
    }: {
      action: string;
      messages: number[];
      parameters?: object;
    }) =>
      postJson<{ changed: number }>(inBox(`/api/mail/actions/${action}`, box), {
        target: { messages },
        parameters,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mail'] }),
  });
}

/** Lets the chosen messages out to Claude once, which proposes a folder for each; the user moves
    those of its proposals they keep. */
export function TriageDialog({
  messages,
  nameOf,
  onDone,
  onClose,
}: {
  messages: Sorted[];
  nameOf: (to: Destination) => string;
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const box = useBox();
  const queryClient = useQueryClient();
  const [kept, setKept] = useState<Set<number>>(new Set());
  const triage = useMutation({
    mutationFn: () =>
      postJson<{ proposals: Proposal[] }>(inBox('/api/mail/actions/mail.triage', box), {
        target: { messages: messages.map((each) => each.id) },
        consent: 'once',
      }),
    onSuccess: ({ proposals }) => setKept(new Set(proposals.map((each) => each.message))),
  });
  const proposals = triage.data?.proposals;
  const move = useMutation({
    mutationFn: async () => {
      const by = new Map<Destination, number[]>();
      for (const { message, to } of proposals ?? []) {
        if (kept.has(message)) by.set(to, [...(by.get(to) ?? []), message]);
      }
      for (const [to, ids] of by) {
        await postJson(inBox('/api/mail/actions/mail.move', box), {
          target: { messages: ids },
          parameters: { to },
        });
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['mail'] }),
    onSuccess: onDone,
  });
  const failure = triage.error ?? move.error;
  const error = failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>;

  if (proposals === undefined) {
    return (
      <Modal heading={t('ai.consent.heading')} onClose={onClose}>
        <p className="text-sm">{t('mail.triageConsent')}</p>
        {error}
        <div className="flex flex-wrap justify-end gap-2">
          <Cancel />
          <button
            type="button"
            className={primaryButton}
            disabled={triage.isPending}
            onClick={() => triage.mutate()}
          >
            {t('ai.consent.once')}
          </button>
        </div>
      </Modal>
    );
  }
  const subjects = new Map(messages.map((each) => [each.id, each]));
  return (
    <Modal heading={t('mail.triageTitle')} onClose={onClose}>
      {proposals.length === 0 ? (
        <p className="text-sm">{t('mail.triageNone')}</p>
      ) : (
        <ul aria-label={t('mail.triageTitle')} className="flex flex-col gap-2">
          {proposals.map(({ message, to }) => {
            const found = subjects.get(message);
            return (
              <li key={message}>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={kept.has(message)}
                    onChange={(event) => {
                      const next = new Set(kept);
                      if (event.target.checked) next.add(message);
                      else next.delete(message);
                      setKept(next);
                    }}
                  />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate">{found?.subject || t('mail.noSubject')}</span>
                    <span className="truncate text-muted">
                      {found?.sender.name || found?.sender.address}
                    </span>
                  </span>
                  <span className="shrink-0 font-semibold">{nameOf(to)}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {error}
      <div className="flex flex-wrap justify-end gap-2">
        <Cancel />
        {proposals.length > 0 && (
          <button
            type="button"
            className={primaryButton}
            disabled={kept.size === 0 || move.isPending}
            onClick={() => move.mutate()}
          >
            {t('mail.triageApply')}
          </button>
        )}
      </div>
    </Modal>
  );
}
