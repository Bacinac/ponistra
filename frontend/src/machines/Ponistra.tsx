import { useState, type FormEvent } from 'react';
import { Cancel, ConfirmDialog, Labelled, Modal } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { dangerButton, field, primaryButton } from '../styles';
import {
  GUEST_NAME,
  useMachine,
  useMachineApi,
  useMachineWrite,
  usePonistra,
  type LinkState,
  type PonistraLink,
} from './api';
import { Fact, Facts, Failure, Loaded, Pill, useFormats, type Tone } from './parts';

const TONES: Record<LinkState, Tone> = {
  'not-enrolled': 'quiet',
  connecting: 'quiet',
  connected: 'ok',
  offline: 'bad',
  revoked: 'bad',
};

const STATES: Record<LinkState, MessageKey> = {
  'not-enrolled': 'machine.ponistra.state.notEnrolled',
  connecting: 'machine.ponistra.state.connecting',
  connected: 'machine.ponistra.state.connected',
  offline: 'machine.ponistra.state.offline',
  revoked: 'machine.ponistra.state.revoked',
};

/** The machine's link to the office's Ponistra, whose Computers module manages it. Enrolling and
 * leaving happen only on the machine's own page: through Ponistra both are refused. */
export function Ponistra() {
  const link = usePonistra();
  return <Loaded query={link}>{(data) => <PonistraParts link={data} />}</Loaded>;
}

function PonistraParts({ link }: { link: PonistraLink }) {
  const { t } = useI18n();
  const format = useFormats();
  const local = !useMachineApi().throughPonistra;
  const [enrolling, setEnrolling] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const leave = useMachineWrite((api) => api.send('DELETE', '/v1/ponistra'));
  const enrolled = link.state !== 'not-enrolled' && link.state !== 'revoked';
  return (
    <Headed
      heading={t('machine.ponistra')}
      action={
        local &&
        (enrolled ? (
          <button
            type="button"
            className={dangerButton}
            disabled={leave.isPending}
            onClick={() => setLeaving(true)}
          >
            {t('machine.ponistra.leave')}
          </button>
        ) : (
          <button type="button" className={primaryButton} onClick={() => setEnrolling(true)}>
            {t('machine.ponistra.enroll')}
          </button>
        ))
      }
    >
      <Facts>
        <Fact label="machine.state">
          <span className="flex flex-wrap items-center gap-2">
            <Pill tone={TONES[link.state]}>{t(STATES[link.state])}</Pill>
            {link.since && (
              <span className="text-xs text-muted">
                {t('machine.ponistra.since')} {format.date(link.since)}
              </span>
            )}
          </span>
        </Fact>
        {link.url && (
          <Fact label="machine.ponistra.url">
            <a href={link.url} className="text-link hover:underline">
              {link.url}
            </a>
          </Fact>
        )}
        {link.enrolled_at && (
          <Fact label="machine.ponistra.enrolledAt">{format.date(link.enrolled_at)}</Fact>
        )}
        {link.error && (
          <Fact label="machine.ponistra.error">
            <span className="text-danger">{link.error}</span>
          </Fact>
        )}
      </Facts>
      {link.recovery_key === 'machine' && (
        <p role="alert" className="text-sm text-danger">
          {t('machine.ponistra.keyOnMachine')}
        </p>
      )}
      {link.backup_password === 'machine' && (
        <p className="text-sm text-muted">{t('machine.ponistra.passwordOnMachine')}</p>
      )}
      <Failure error={leave.error} />
      {enrolling && <Enroll link={link} onClose={() => setEnrolling(false)} />}
      {leaving && (
        <ConfirmDialog
          heading={t('machine.ponistra.leave')}
          confirmLabel={t('machine.ponistra.leave')}
          onConfirm={() => leave.mutate(undefined)}
          onClose={() => setLeaving(false)}
        >
          {t('machine.ponistra.leaveText')}
        </ConfirmDialog>
      )}
    </Headed>
  );
}

function Enroll({ link, onClose }: { link: PonistraLink; onClose: () => void }) {
  const { t } = useI18n();
  const machine = useMachine();
  const [code, setCode] = useState('');
  const [url, setUrl] = useState(link.url ?? '');
  const [name, setName] = useState(machine.data?.hostname ?? '');
  const enroll = useMachineWrite(
    (api, body: object) => api.send('POST', '/v1/ponistra/enroll', body),
    onClose,
  );
  const valid = /^[A-Za-z0-9-]{6,64}$/.test(code.trim()) && (!name || GUEST_NAME.test(name));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    enroll.mutate({
      code: code.trim(),
      ...(url.trim() && { url: url.trim() }),
      ...(name.trim() && { name: name.trim() }),
    });
  };
  const input = (
    label: string,
    value: string,
    set: (value: string) => void,
    props: { type?: string; placeholder?: string; autoFocus?: boolean } = {},
  ) => (
    <Labelled label={label}>
      {(id) => (
        <input
          id={id}
          value={value}
          onChange={(event) => set(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          className={field}
          {...props}
        />
      )}
    </Labelled>
  );
  return (
    <Modal heading={t('machine.ponistra.enroll')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {input(t('machine.ponistra.code'), code, setCode, { autoFocus: true })}
        {input(t('machine.ponistra.url'), url, setUrl, { type: 'url', placeholder: 'https://' })}
        {input(t('machine.name'), name, setName)}
        <Failure error={enroll.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || enroll.isPending}>
            {t('machine.ponistra.enroll')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** The machine's name, which an enrolled machine first asks its Ponistra for: Ponistra refuses a
 * name another of its computers has. */
export function RenameMachine({ current, onClose }: { current: string; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(current);
  const rename = useMachineWrite(
    (api, given: string) => api.send('PUT', '/v1/machine/name', { name: given }),
    onClose,
  );
  const valid = GUEST_NAME.test(name) && name !== current;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (valid) rename.mutate(name);
  };
  return (
    <Modal heading={t('machine.rename')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('machine.name')}>
          {(id) => (
            <input
              id={id}
              value={name}
              onChange={(event) => setName(event.target.value)}
              onFocus={(event) => event.currentTarget.select()}
              autoFocus
              maxLength={63}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={name !== '' && !GUEST_NAME.test(name)}
              className={field}
            />
          )}
        </Labelled>
        <Failure error={rename.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || rename.isPending}>
            {t('machine.rename')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
