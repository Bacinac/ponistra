import { PhoneOff, Video } from 'lucide-react';
import { useEffect, useId, useReducer, useState } from 'react';
import { useLocation } from 'react-router';
import { postJson } from './api';
import { useI18n } from './i18n';
import { useLive } from './live';
import { useMeetingWindow } from './meetingWindow';
import { dangerButton, primaryButton } from './styles';

// Two notes of a chime, every few seconds while it rings.
const NOTES = [660, 880];
const NOTE = 0.45;
const EVERY = 3000;

/** The chime, where the browser lets the page sound: once the user has done something on it. */
function useRingTone(on: boolean): void {
  useEffect(() => {
    if (!on || !navigator.userActivation.hasBeenActive) return;
    const context = new AudioContext();
    const chime = () => {
      NOTES.forEach((frequency, at) => {
        const start = context.currentTime + at * NOTE;
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.2, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + NOTE);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start(start);
        oscillator.stop(start + NOTE);
      });
      navigator.vibrate?.([400, 200, 400]);
    };
    chime();
    const timer = setInterval(chime, EVERY);
    return () => {
      clearInterval(timer);
      navigator.vibrate?.(0);
      void context.close();
    };
  }, [on]);
}

/** A colleague's call into a meeting over whatever page is open, ringing until it is answered,
 * declined or stops; answered, the user is in the meeting at once, as on a telephone. */
export function Ringing() {
  const { t } = useI18n();
  const meetingWindow = useMeetingWindow();
  const { pathname } = useLocation();
  const { ringing, at } = useLive();
  const heading = useId();
  // Answered or declined here, a ring is not shown again while the answer reaches the server.
  const [handled, setHandled] = useState<ReadonlySet<number>>(new Set());
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  const now = Date.now();
  const shown = ringing.find(
    (each) =>
      at + each.left * 1000 > now && !handled.has(each.id) && pathname !== `/meet/${each.meeting}`,
  );
  useRingTone(!!shown);
  useEffect(() => {
    if (!shown) return;
    const timer = setTimeout(redraw, at + shown.left * 1000 - Date.now());
    return () => clearTimeout(timer);
  }, [shown, at]);
  if (!shown) return null;

  const handle = () => setHandled((before) => new Set(before).add(shown.id));
  const decline = () => {
    handle();
    void postJson(`/api/meetings/${shown.meeting}/decline`);
  };
  const answer = () => {
    handle();
    meetingWindow.open(`/meet/${shown.meeting}?answered`);
  };
  return (
    <div
      role="alertdialog"
      aria-labelledby={heading}
      className="fixed top-4 left-1/2 z-50 flex w-[min(24rem,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-3 rounded-lg border border-line bg-raised p-4 text-ink shadow-xl"
    >
      <div className="flex min-w-0 flex-col">
        <p id={heading} className="font-semibold">
          {t('ring.calls').replace('{by}', shown.by)}
        </p>
        {shown.title && <p className="truncate text-sm text-muted">{shown.title}</p>}
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={decline} className={dangerButton}>
          <PhoneOff size={16} aria-hidden />
          {t('ring.decline')}
        </button>
        <button type="button" onClick={answer} className={primaryButton}>
          <Video size={16} aria-hidden />
          {t('meeting.join')}
        </button>
      </div>
    </div>
  );
}
