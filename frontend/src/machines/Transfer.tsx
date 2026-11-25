import { useState, type FormEvent } from 'react';
import { Cancel, Close, Labelled, Modal } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import { useGuests, useMachineWrite } from './api';
import { Failure, useFormats } from './parts';

/** Guests moving between machines by Incus's migration: the receiving machine gives a token,
 * the sending one is given it. */
export function Transfer() {
  const { t } = useI18n();
  const [receiving, setReceiving] = useState(false);
  const [sending, setSending] = useState(false);
  return (
    <Headed
      heading={t('machine.transfer')}
      action={
        <div className="flex flex-wrap gap-2">
          <button type="button" className={button} onClick={() => setReceiving(true)}>
            {t('machine.transfer.receive')}
          </button>
          <button type="button" className={button} onClick={() => setSending(true)}>
            {t('machine.transfer.send')}
          </button>
        </div>
      }
    >
      {receiving && <Receive onClose={() => setReceiving(false)} />}
      {sending && <Send onClose={() => setSending(false)} />}
    </Headed>
  );
}

function Receive({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const format = useFormats();
  const [copied, setCopied] = useState(false);
  const open = useMachineWrite((api) =>
    api.send<{ token: string; expires_at: string }>('POST', '/v1/transfer/receive'),
  );
  return (
    <Modal heading={t('machine.transfer.receive')} onClose={onClose}>
      <p className="text-sm">{t('machine.transfer.receiveText')}</p>
      {open.data ? (
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex items-start gap-2">
            <code className="min-w-0 flex-1 rounded border border-line bg-panel px-2 py-1.5 font-mono text-xs break-all">
              {open.data.token}
            </code>
            <button
              type="button"
              className={button}
              onClick={() =>
                navigator.clipboard.writeText(open.data!.token).then(() => setCopied(true))
              }
            >
              {t(copied ? 'machine.import.copied' : 'machine.import.copy')}
            </button>
          </div>
          <span className="text-muted">
            {t('machine.transfer.until')} {format.date(open.data.expires_at)}
          </span>
        </div>
      ) : (
        <Failure error={open.error} />
      )}
      <div className="flex justify-end gap-2">
        {open.data ? (
          <Close />
        ) : (
          <>
            <Cancel />
            <button
              type="button"
              className={primaryButton}
              disabled={open.isPending}
              onClick={() => open.mutate(undefined)}
            >
              {t('machine.transfer.token')}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}

function Send({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const guests = useGuests();
  const [token, setToken] = useState('');
  const [chosen, setChosen] = useState<string[]>([]);
  const [volumes, setVolumes] = useState('');
  const [move, setMove] = useState(false);
  const send = useMachineWrite(
    (api, body: object) => api.send('POST', '/v1/transfer/send', body),
    onClose,
  );
  const listed = volumes
    .split(/[\s,]+/)
    .map((each) => each.trim())
    .filter(Boolean);
  const valid = token.trim() !== '' && (chosen.length > 0 || listed.length > 0);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    send.mutate({
      token: token.trim(),
      ...(chosen.length > 0 && { guests: chosen }),
      ...(listed.length > 0 && { volumes: listed }),
      ...(move && { move: true }),
    });
  };
  return (
    <Modal heading={t('machine.transfer.send')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('machine.transfer.tokenGiven')}>
          {(id) => (
            <input
              id={id}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoFocus
              autoComplete="off"
              spellCheck={false}
              className={field}
            />
          )}
        </Labelled>
        <fieldset className="flex flex-col gap-1 text-sm">
          <legend className="mb-1 text-muted">{t('machine.guests')}</legend>
          {guests.data?.map((guest) => (
            <label key={guest.name} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={chosen.includes(guest.name)}
                onChange={(event) =>
                  setChosen(
                    event.target.checked
                      ? [...chosen, guest.name]
                      : chosen.filter((each) => each !== guest.name),
                  )
                }
              />
              {guest.name}
              <span className="text-xs text-muted">{guest.status}</span>
            </label>
          ))}
          <Failure error={guests.error} />
        </fieldset>
        <Labelled label={t('machine.transfer.volumes')}>
          {(id) => (
            <input
              id={id}
              value={volumes}
              onChange={(event) => setVolumes(event.target.value)}
              spellCheck={false}
              className={field}
            />
          )}
        </Labelled>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={move}
            onChange={(event) => setMove(event.target.checked)}
          />
          <span>
            {t('machine.transfer.move')}
            <span className="block text-xs text-muted">
              {t(move ? 'machine.transfer.moveText' : 'machine.transfer.copyText')}
            </span>
          </span>
        </label>
        <Failure error={send.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || send.isPending}>
            {t('machine.transfer.start')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
