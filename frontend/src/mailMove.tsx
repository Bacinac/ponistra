import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useState } from 'react';
import { Cancel, Labelled, Modal } from './dialogs';
import { useI18n } from './i18n';
import { runJob } from './jobs';
import { type Account, accountName, useBox } from './mailData';
import { field, primaryButton } from './styles';
import { errorMessage } from './tree';

/** The accounts the account's mail can move into: the others reached over IMAP. */
export function movesInto(account: Account, accounts: Account[]): Account[] {
  return accounts.filter((each) => each.id !== account.id && each.protocol === 'imap');
}

/** Moves the mail the account brought into another account at its provider (S3-8), in the
    server's queue: it goes on with the dialog closed and after a restart. */
export function MoveMailDialog({
  account,
  accounts,
  onClose,
}: {
  account: Account;
  accounts: Account[];
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const box = useBox();
  const queryClient = useQueryClient();
  const into = movesInto(account, accounts);
  const [to, setTo] = useState(into[0]?.id ?? null);
  const move = useMutation({
    mutationFn: (target: number) =>
      runJob<{ moved: number }>(
        'mail-move',
        { from: account.id, to: target, ...(box !== null && { box }) },
        accountName(account),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['mail'] }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (to !== null) move.mutate(to);
  }

  return (
    <Modal heading={`${t('mail.moveMail')} ${accountName(account)}`} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('mail.moveMailTo')}>
          {(id) => (
            <select
              id={id}
              value={to ?? ''}
              disabled={move.isPending || move.isSuccess}
              onChange={(event) => setTo(Number(event.target.value))}
              className={field}
            >
              {into.map((each) => (
                <option key={each.id} value={each.id}>
                  {accountName(each)}
                </option>
              ))}
            </select>
          )}
        </Labelled>
        {move.isSuccess && (
          <p role="status" className="text-sm">
            {t('mail.moveMailDone').replace('{count}', formatNumber(move.data.moved))}
          </p>
        )}
        {move.isError && <p className="text-sm text-danger">{errorMessage(move.error, t)}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Cancel />
          {!move.isSuccess && (
            <button
              type="submit"
              className={primaryButton}
              disabled={to === null || move.isPending}
            >
              {t('mail.moveMailStart')}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}
