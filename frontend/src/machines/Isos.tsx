import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { ConfirmDialog } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, iconButton } from '../styles';
import { ISO_NAME, useIsos, useMachineApi, useMachineWrite } from './api';
import { Failure, Loaded, Meter, table, useFormats } from './parts';

/** The installation images guests are made from (a recipe's `iso` input), sent to the machine
 * as they are. */
export function Isos() {
  const { t } = useI18n();
  const format = useFormats();
  const api = useMachineApi();
  const client = useQueryClient();
  const isos = useIsos();
  const [sending, setSending] = useState<{ name: string; share: number } | null>(null);
  const [failed, setFailed] = useState<Error | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const remove = useMachineWrite((machine, name: string) =>
    machine.send('DELETE', `/v1/isos/${encodeURIComponent(name)}`),
  );

  const send = async (file: File) => {
    const name = file.name.replace(/[^A-Za-z0-9._-]/g, '-').slice(-63);
    setFailed(null);
    if (!ISO_NAME.test(name)) {
      setFailed(new Error(t('machine.iso.nameRule')));
      return;
    }
    setSending({ name, share: 0 });
    try {
      await api.upload(`/v1/isos?${new URLSearchParams({ name })}`, file, (share) =>
        setSending({ name, share }),
      );
    } catch (error) {
      setFailed(error as Error);
    } finally {
      setSending(null);
      void client.invalidateQueries({ queryKey: ['machine', api.base] });
    }
  };
  const picker = useRef<HTMLInputElement>(null);

  return (
    <Headed
      heading={t('machine.isos')}
      action={
        <>
          <input
            ref={picker}
            type="file"
            accept=".iso,application/x-iso9660-image"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void send(file);
            }}
          />
          <button
            type="button"
            className={button}
            disabled={!!sending}
            onClick={() => picker.current?.click()}
          >
            {t('machine.iso.upload')}
          </button>
        </>
      }
    >
      {sending && (
        <div role="status" className="flex flex-col gap-1 text-sm">
          <span>
            {t('machine.iso.sending')} {sending.name}
          </span>
          <Meter share={sending.share * 100} label={sending.name} />
        </div>
      )}
      <Failure error={failed} />
      <Failure error={remove.error} />
      <Loaded query={isos}>
        {(data) =>
          data.length === 0 ? (
            <p className="text-sm text-muted">{t('machine.isos.none')}</p>
          ) : (
            <table className={table}>
              <thead>
                <tr>
                  <th>{t('machine.iso')}</th>
                  <th>{t('machine.size')}</th>
                  <th>{t('machine.iso.added')}</th>
                  <th>
                    <span className="sr-only">{t('machine.actions')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((iso) => (
                  <tr key={iso.name}>
                    <td className="font-mono text-xs">{iso.name}</td>
                    <td className="tabular-nums">{format.bytes(iso.size)}</td>
                    <td>{format.date(iso.created_at)}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        className={iconButton}
                        disabled={remove.isPending}
                        onClick={() => setAsked(iso.name)}
                      >
                        {t('machine.iso.delete')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </Loaded>
      {asked && (
        <ConfirmDialog
          heading={t('machine.iso.deleteHeading')}
          confirmLabel={t('machine.iso.delete')}
          onConfirm={() => remove.mutate(asked)}
          onClose={() => setAsked(null)}
        >
          {t('machine.iso.deleteText').replace('{name}', asked)}
        </ConfirmDialog>
      )}
    </Headed>
  );
}
