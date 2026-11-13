import { useQueryClient } from '@tanstack/react-query';
import { AudioLines, ImagePlus, Lightbulb, Mic, ScanFace, Trash2, Wallpaper } from 'lucide-react';
import { useState } from 'react';
import { ApiError, deleteJson, patchJson, putBytes } from './api';
import { type Session, SESSION_KEY, useSession } from './auth';
import {
  BACKDROPS,
  type Background,
  type CallChoices,
  SHAPEABLE,
  type ShapingState,
  UNCHOSEN,
} from './camera';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { MenuChoices, MenuItem, MenuSeparator, MenuSub } from './menu';
import { button } from './styles';
import { errorMessage } from './tree';

const GUEST_KEY = 'ponistra.call';
const DEVICES_KEY = 'ponistra.devices';
const BACKDROP = '/api/auth/backdrop';
// What the browser sends of a picture of the user's own: enough for a call's picture.
const BACKDROP_SIZE = { width: 1920, height: 1080 };

export type Kind = 'audioinput' | 'videoinput' | 'audiooutput';

function read<T>(key: string, fallback: T): T {
  try {
    return { ...fallback, ...JSON.parse(localStorage.getItem(key) ?? '{}') };
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // A browser that keeps nothing asks again next time.
  }
}

/** The camera, microphone and speaker this device last used, kept by the device alone: another
    device has others. */
export function keptDevice(kind: Kind): { ideal: string } | undefined {
  const device = read<Partial<Record<Kind, string>>>(DEVICES_KEY, {})[kind];
  return device ? { ideal: device } : undefined;
}

export function keepDevice(kind: Kind, device: string) {
  write(DEVICES_KEY, { ...read(DEVICES_KEY, {}), [kind]: device });
}

export interface Look {
  choices: CallChoices;
  /** The address of the user's own picture behind them, where they have one. */
  own: string | null;
  /** Whether a picture of one's own can be kept: a guest has no account to keep it. */
  ownable: boolean;
  choose: (given: Partial<CallChoices>) => void;
  keepOwn: (file: File | null) => Promise<void>;
}

/** What a call does with the camera and the microphone: the account keeps it for every device, a
    guest's browser for the guest. */
export function useLook(guest: boolean): Look {
  const queryClient = useQueryClient();
  const user = useSession().data?.user;
  const [guests, setGuests] = useState(() => read(GUEST_KEY, UNCHOSEN));
  if (guest || !user)
    return {
      choices: guests,
      own: null,
      ownable: false,
      choose: (given) => {
        const next = { ...guests, ...given };
        setGuests(next);
        write(GUEST_KEY, next);
      },
      keepOwn: async () => {},
    };
  const choices = { ...UNCHOSEN, ...user.call };
  const kept = (session: Session) => queryClient.setQueryData(SESSION_KEY, session);
  // The account keeps the choices whole; a refused one leaves them as they were, which the
  // session shows again.
  const choose = (given: Partial<CallChoices>) => {
    const call = { ...user.call, ...given };
    queryClient.setQueryData<Session>(SESSION_KEY, (session) =>
      session?.user ? { ...session, user: { ...session.user, call } } : session,
    );
    void patchJson<Session>('/api/auth/preferences', { call }).then(kept, () =>
      queryClient.invalidateQueries({ queryKey: SESSION_KEY }),
    );
  };
  return {
    choices,
    own: user.backdrop ? `${BACKDROP}?v=${user.backdrop.slice(0, 12)}` : null,
    ownable: true,
    choose,
    keepOwn: async (file) => {
      if (!file) {
        await deleteJson(BACKDROP);
        await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
        return;
      }
      kept(await putBytes<Session>(BACKDROP, await smaller(file)));
      choose({ background: 'own' });
    },
  };
}

/** The picture drawn no larger than a call shows it, as JPEG. */
async function smaller(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file).catch(() => {
    throw new ApiError(BACKDROP, 415, 'not_a_photo');
  });
  const scale = Math.min(
    1,
    BACKDROP_SIZE.width / bitmap.width,
    BACKDROP_SIZE.height / bitmap.height,
  );
  const canvas = new OffscreenCanvas(
    Math.round(bitmap.width * scale),
    Math.round(bitmap.height * scale),
  );
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.convertToBlob({ type: 'image/jpeg', quality: 0.86 });
}

const BACKGROUNDS: { value: Background; label: MessageKey }[] = [
  { value: 'none', label: 'meeting.background.none' },
  { value: 'soft', label: 'meeting.background.soft' },
  { value: 'strong', label: 'meeting.background.strong' },
  ...(Object.keys(BACKDROPS) as (keyof typeof BACKDROPS)[]).map((value) => ({
    value,
    label: `meeting.background.${value}` as MessageKey,
  })),
];

/** The camera's and the microphone's processing, in the menu of the devices. Choosing a picture
    of one's own opens the file picker the caller holds. */
export function LookItems({ look, onPick }: { look: Look; onPick: () => void }) {
  const { t } = useI18n();
  const { choices, choose } = look;
  const unshapeable = SHAPEABLE ? undefined : t('meeting.unshapeable');
  const backgrounds = look.own
    ? [...BACKGROUNDS, { value: 'own' as const, label: 'meeting.background.own' as const }]
    : BACKGROUNDS;
  return (
    <>
      <MenuSeparator />
      <MenuSub
        icon={Wallpaper}
        label={t('meeting.background')}
        disabled={!SHAPEABLE}
        hint={unshapeable}
      >
        <MenuChoices
          value={choices.background}
          choices={backgrounds.map(({ value, label }) => ({ value, label: t(label) }))}
          onChange={(background) => choose({ background })}
        />
        {look.ownable && (
          <>
            <MenuSeparator />
            <MenuItem icon={ImagePlus} label={t('meeting.backdropUpload')} onSelect={onPick} />
            {look.own && (
              <MenuItem
                icon={Trash2}
                label={t('meeting.backdropRemove')}
                onSelect={() => void look.keepOwn(null)}
              />
            )}
          </>
        )}
      </MenuSub>
      <MenuItem
        icon={ScanFace}
        label={t('meeting.framing')}
        checked={choices.framing}
        disabled={!SHAPEABLE}
        hint={unshapeable}
        onSelect={() => choose({ framing: !choices.framing })}
      />
      <MenuItem
        icon={Lightbulb}
        label={t('meeting.light')}
        checked={choices.light}
        disabled={!SHAPEABLE}
        hint={unshapeable}
        onSelect={() => choose({ light: !choices.light })}
      />
      <MenuSub icon={Mic} label={t('meeting.sound')}>
        {(['noise', 'echo', 'gain'] as const).map((key) => (
          <MenuItem
            key={key}
            icon={AudioLines}
            label={t(`meeting.${key}`)}
            checked={choices[key]}
            onSelect={() => choose({ [key]: !choices[key] })}
          />
        ))}
      </MenuSub>
    </>
  );
}

/** What the camera's processing gave up or failed at, said where the user sees their picture. */
export function ShapingNotice({ state, onRetry }: { state: ShapingState; onRetry: () => void }) {
  const { t } = useI18n();
  if (!state.dropped && !state.error) return null;
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 bg-panel px-4 py-1 text-sm">
      <p className="flex-1 text-danger">
        {state.error
          ? `${t('meeting.shapingFailed')}: ${errorMessage(state.error, t)}`
          : t(
              state.dropped === 'background' ? 'meeting.strainedBackground' : 'meeting.strainedAll',
            )}
      </p>
      <button type="button" onClick={onRetry} className={button}>
        {t('meeting.retry')}
      </button>
    </div>
  );
}
