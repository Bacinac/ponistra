import { useMutation } from '@tanstack/react-query';
import { RotateCw, Share2, UserPlus } from 'lucide-react';
import { useEffect, useReducer, useState, type FormEvent } from 'react';
import { postJson } from './api';
import { Cancel, Close, Labelled, Modal } from './dialogs';
import { useI18n } from './i18n';
import { useLive, type Rung } from './live';
import { CopyLink, type Meeting } from './meeting';
import { Recipients } from './recipients';
import { button, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import type { Person } from './mailData';

interface Invited {
  rung: string[];
  written: string[];
}

function useInvite(meeting: string) {
  const { language } = useI18n();
  return useMutation({
    mutationFn: (people: Person[]) =>
      postJson<Invited>(`/api/meetings/${meeting}/invite`, { people, language }),
  });
}

/** Asks people into a meeting made on its own; a planned meeting asks them through its event.
    `ready` makes a meeting made now that nothing has used yet. */
export function AddPeople({
  meeting,
  ready,
}: {
  meeting: Meeting;
  ready?: () => Promise<Meeting>;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState<Meeting | null>(null);
  const opening = useMutation({
    mutationFn: async () => (ready ? ready() : meeting),
    onSuccess: setOpen,
  });
  return (
    <>
      <button
        type="button"
        onClick={() => opening.mutate()}
        disabled={opening.isPending}
        className={button}
      >
        <UserPlus size={16} aria-hidden />
        <span className="sr-only sm:not-sr-only">{t('invite.add')}</span>
      </button>
      {opening.isError && <p className="text-sm text-danger">{errorMessage(opening.error, t)}</p>}
      {open && <InviteDialog meeting={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function InviteDialog({ meeting, onClose }: { meeting: Meeting; onClose: () => void }) {
  const { t } = useI18n();
  const [people, setPeople] = useState<Person[]>([]);
  const [told, setTold] = useState('');
  const invite = useInvite(meeting.id);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    invite.mutate(people, {
      onSuccess: ({ rung, written }) => {
        setTold(
          [
            rung.length ? `${t('invite.rung')}: ${rung.join(', ')}.` : '',
            written.length ? `${t('invite.written')}: ${written.join(', ')}.` : '',
          ]
            .filter(Boolean)
            .join(' '),
        );
        setPeople([]);
      },
    });
  };
  const share = () =>
    void navigator
      .share({ title: meeting.title || t('meeting.untitled'), url: meeting.link })
      .catch((error: Error) => {
        if (error.name !== 'AbortError') throw error;
      });
  return (
    <Modal heading={t('invite.add')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('invite.people')}>
          {(id) => <Recipients id={id} people={people} onChange={setPeople} autoFocus />}
        </Labelled>
        <p className="text-xs text-muted">{t('invite.how')}</p>
        {invite.error && <p className="text-sm text-danger">{errorMessage(invite.error, t)}</p>}
        {told && (
          <p role="status" className="text-sm">
            {told}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <CopyLink link={meeting.link} />
          {'share' in navigator && (
            <button type="button" onClick={share} className={button}>
              <Share2 size={16} aria-hidden />
              {t('invite.share')}
            </button>
          )}
          <div className="ml-auto flex gap-2">
            {told ? <Close /> : <Cancel />}
            <button
              type="submit"
              disabled={people.length === 0 || invite.isPending}
              className={primaryButton}
            >
              {t('invite.send')}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

/** How the colleagues the user rang into the meeting answer; whoever joined is in it. */
export function Rings({ meeting }: { meeting: string }) {
  const { t } = useI18n();
  const { rung, at } = useLive();
  const again = useInvite(meeting);
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  const latest = new Map<string, Rung>();
  for (const each of rung) if (each.meeting === meeting) latest.set(each.address, each);
  const shown = [...latest.values()].filter((each) => each.answer !== 'joined');
  const now = Date.now();
  const sounding = (each: Rung) => !each.answer && at + each.left * 1000 > now;
  const stops = Math.min(...shown.filter(sounding).map((each) => at + each.left * 1000));
  useEffect(() => {
    if (!Number.isFinite(stops)) return;
    const timer = setTimeout(redraw, stops - Date.now());
    return () => clearTimeout(timer);
  }, [stops]);
  if (shown.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <ul aria-label={t('invite.rings')} className="flex flex-wrap gap-2 text-sm">
        {shown.map((each) => (
          <li
            key={each.address}
            className="flex min-w-0 items-center gap-2 rounded-full bg-panel py-1 pr-1 pl-3"
          >
            <span className="truncate">{each.name}</span>
            <span className="text-muted">
              {t(
                sounding(each)
                  ? 'invite.ringing'
                  : each.answer === 'declined'
                    ? 'invite.declined'
                    : 'invite.missed',
              )}
            </span>
            {sounding(each) ? (
              <span className="w-1" />
            ) : (
              <button
                type="button"
                onClick={() => again.mutate([{ name: each.name, address: each.address }])}
                disabled={again.isPending}
                title={t('invite.again')}
                aria-label={`${t('invite.again')}: ${each.name}`}
                className={iconButton}
              >
                <RotateCw size={14} aria-hidden />
              </button>
            )}
          </li>
        ))}
      </ul>
      {again.error && <p className="text-sm text-danger">{errorMessage(again.error, t)}</p>}
    </div>
  );
}
