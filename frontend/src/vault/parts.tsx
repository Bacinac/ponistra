import { Check, Copy, Download, Eye, EyeOff, FileKey2, KeyRound, StickyNote } from 'lucide-react';
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { useI18n } from '../i18n';
import { button, field, iconButton, primaryButton } from '../styles';

const CLEARED = 30_000;
export const KIND_ICONS = { login: KeyRound, note: StickyNote, mailkey: FileKey2 };
export const SHORTEST = 12;

let copies = 0;

/** Text put on the clipboard and taken off it after half a minute, unless something else from
    the vault was copied since. */
export async function copied(text: string): Promise<void> {
  const copy = ++copies;
  await navigator.clipboard.writeText(text);
  setTimeout(() => {
    if (copy === copies) navigator.clipboard.writeText('').catch(() => undefined);
  }, CLEARED);
}

export function saved(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function CopyButton({
  text,
  label,
  onCopied,
}: {
  text: string;
  label: string;
  onCopied?: () => void;
}) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!done) return;
    const timer = setTimeout(() => setDone(false), 1500);
    return () => clearTimeout(timer);
  }, [done]);
  return (
    <button
      type="button"
      aria-label={label}
      title={failed ? t('clipboard.denied') : label}
      onClick={() =>
        copied(text).then(
          () => {
            setFailed(false);
            setDone(true);
            onCopied?.();
          },
          () => setFailed(true),
        )
      }
      className={`${iconButton} ${failed ? 'text-danger' : ''}`}
    >
      {done ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
    </button>
  );
}

export function RevealButton({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      aria-label={t(shown ? 'vault.hide' : 'vault.show')}
      aria-pressed={shown}
      title={t(shown ? 'vault.hide' : 'vault.show')}
      onClick={onToggle}
      className={iconButton}
    >
      {shown ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
    </button>
  );
}

/** A recovery code shown once, to be kept outside PONISTRA. */
export function CodeShown({ code, note }: { code: string; note: string }) {
  const { t, formatDay } = useI18n();
  const text = `Ponistra – ${t('vault.code')} – ${location.host} – ${formatDay(new Date())}\n${code}\n`;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">{note}</p>
      <p
        aria-label={t('vault.code')}
        className="rounded border border-line bg-panel p-3 text-center font-mono text-lg tracking-wider break-all select-all"
      >
        {code}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void navigator.clipboard.writeText(code)}
          className={button}
        >
          <Copy size={16} aria-hidden />
          {t('health.kit.copy')}
        </button>
        <button
          type="button"
          onClick={() =>
            saved(
              new Blob([text], { type: 'text/plain' }),
              `ponistra-${location.host}-vault-code.txt`,
            )
          }
          className={button}
        >
          <Download size={16} aria-hidden />
          {t('health.kit.download')}
        </button>
      </div>
    </div>
  );
}

/** A new vault password typed twice, at least as long as SHORTEST. */
export function NewPassword({
  submitLabel,
  pending,
  error,
  onSubmit,
  children,
}: {
  submitLabel: string;
  pending: boolean;
  error: ReactNode;
  onSubmit: (password: string) => void;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [shown, setShown] = useState(false);
  const id = useId();
  const short = password.length > 0 && [...password].length < SHORTEST;
  const differs = again.length > 0 && again !== password;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (short || again !== password) return;
    onSubmit(password);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="flex flex-col gap-1 text-sm">
        <label htmlFor={id}>{t('vault.password.new')}</label>
        <span className="flex items-center gap-1">
          <input
            id={id}
            type={shown ? 'text' : 'password'}
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={short}
            aria-describedby={`${id}-hint`}
            className={`${field} min-w-0 flex-1`}
          />
          <RevealButton shown={shown} onToggle={() => setShown(!shown)} />
        </span>
        <span id={`${id}-hint`} className={`text-xs ${short ? 'text-danger' : 'text-muted'}`}>
          {t('vault.password.shortest')}
        </span>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        {t('vault.password.again')}
        <input
          type={shown ? 'text' : 'password'}
          autoComplete="new-password"
          required
          value={again}
          onChange={(event) => setAgain(event.target.value)}
          aria-invalid={differs}
          className={field}
        />
        {differs && <span className="text-xs text-danger">{t('vault.password.differs')}</span>}
      </label>
      {children}
      {error}
      <div className="flex justify-end gap-2">
        <button
          type="submit"
          disabled={pending || short || differs || !password}
          className={primaryButton}
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
