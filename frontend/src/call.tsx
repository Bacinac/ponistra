import { useMutation } from '@tanstack/react-query';
import {
  ConnectionState,
  createLocalAudioTrack,
  createLocalVideoTrack,
  DisconnectReason,
  type LocalAudioTrack,
  type LocalVideoTrack,
  type Participant,
  Room,
  RoomEvent,
  Track,
  type TrackPublication,
  VideoPresets,
} from 'livekit-client';
import {
  MessageSquare,
  Mic,
  MicOff,
  Monitor,
  MonitorUp,
  PhoneOff,
  Settings,
  Speaker,
  Users,
  Video,
  VideoOff,
  Volume2,
} from 'lucide-react';
import { useEffect, useReducer, useRef, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { postJson } from './api';
import { Conversation, useMemberTalk, type Talk } from './chat';
import { useWide } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { AtDoor, type Guesting, type Joining } from './guest';
import { resound, Shaping, type ShapingState, soundOf, type CallChoices } from './camera';
import {
  keepDevice,
  keptDevice,
  type Kind,
  type Look,
  LookItems,
  ShapingNotice,
  useLook,
} from './callChoices';
import { AddPeople, Rings } from './invite';
import { CopyLink } from './meeting';
import { hasScreens, isBeside, toNextScreen } from './meetingWindow';
import type { Shown } from './MeetingPage';
import { Menu, MenuChoices, MenuSub } from './menu';
import { useReachable } from './live';
import { initials } from './people';
import { Recordings, useRecording } from './recording';
import { useHeldRelease } from './release';
import { button, dangerButton, field, primaryButton } from './styles';
import { errorMessage } from './tree';

type Stage = 'before' | 'inside' | 'left' | 'dropped';

const KINDS: { kind: Kind; label: MessageKey; icon: typeof Mic }[] = [
  { kind: 'videoinput', label: 'meeting.camera', icon: Video },
  { kind: 'audioinput', label: 'meeting.microphone', icon: Mic },
  { kind: 'audiooutput', label: 'meeting.speaker', icon: Speaker },
];

// Every change of the room that changes what is drawn.
const REDRAWN = [
  RoomEvent.ParticipantConnected,
  RoomEvent.ParticipantDisconnected,
  RoomEvent.TrackSubscribed,
  RoomEvent.TrackUnsubscribed,
  RoomEvent.TrackMuted,
  RoomEvent.TrackUnmuted,
  RoomEvent.LocalTrackPublished,
  RoomEvent.LocalTrackUnpublished,
  RoomEvent.ActiveSpeakersChanged,
  RoomEvent.ParticipantNameChanged,
  RoomEvent.ConnectionStateChanged,
  RoomEvent.AudioPlaybackStatusChanged,
  RoomEvent.ActiveDeviceChanged,
] as const;

interface Own {
  audio?: LocalAudioTrack;
  video?: LocalVideoTrack;
  /** Why the browser gave no camera or microphone, where it gave neither. */
  refused?: boolean;
}

function signalling(): string {
  return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/livekit`;
}

/** The camera and the microphone the browser gives, each where it gives it, those this device
    used last where it still has them. */
async function taken(choices: CallChoices): Promise<Own> {
  const [audio, video] = await Promise.allSettled([
    createLocalAudioTrack({ ...soundOf(choices), deviceId: keptDevice('audioinput') }),
    createLocalVideoTrack({
      resolution: VideoPresets.h720.resolution,
      deviceId: keptDevice('videoinput'),
    }),
  ]);
  return {
    audio: audio.status === 'fulfilled' ? audio.value : undefined,
    video: video.status === 'fulfilled' ? video.value : undefined,
    refused: audio.status === 'rejected' && video.status === 'rejected',
  };
}

export default function Call({
  meeting,
  make,
  guest,
  onInside,
}: {
  meeting: Shown;
  /** Makes a meeting made now as it is first used. */
  make?: () => Promise<Shown>;
  /** Someone outside the installation, who comes in as a guest. */
  guest?: Guesting;
  onInside: (inside: boolean) => void;
}) {
  const ready = async () => (make ? make() : meeting);
  const [own, setOwn] = useState<Own | null>(null);
  const [room, setRoom] = useState<Room | null>(null);
  const [stage, setStage] = useState<Stage>('before');
  const ownRef = useRef(own);
  ownRef.current = own;
  const look = useLook(!!guest);
  const [notice, setNotice] = useState<ShapingState>({ dropped: null, error: null });
  const shapingRef = useRef<Shaping | null>(null);
  shapingRef.current ??= new Shaping(look.choices, look.own, setNotice);
  const shaping = shapingRef.current;
  const chosen = JSON.stringify(look.choices);
  useEffect(() => shaping.choose(JSON.parse(chosen), look.own), [shaping, chosen, look.own]);

  // The browser processes the sound of a microphone as it is taken, so a changed choice takes it
  // anew; one turned on later in the call follows the room's defaults.
  const sound = soundOf(look.choices);
  const heard = JSON.stringify(sound);
  const lastHeard = useRef(heard);
  useEffect(() => {
    if (lastHeard.current === heard) return;
    lastHeard.current = heard;
    const given: CallChoices = { ...JSON.parse(chosen) };
    if (room)
      room.options.audioCaptureDefaults = { ...room.options.audioCaptureDefaults, ...sound };
    const microphone = room
      ? (room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track as
          LocalAudioTrack | undefined)
      : ownRef.current?.audio;
    if (microphone)
      void resound(microphone, given).catch((error: Error) => setNotice({ dropped: null, error }));
  });

  useEffect(() => {
    let live = true;
    void taken(look.choices).then((found) => {
      if (live) setOwn(found);
      else {
        found.audio?.stop();
        found.video?.stop();
      }
    });
    return () => {
      live = false;
      ownRef.current?.audio?.stop();
      ownRef.current?.video?.stop();
    };
  }, []);

  useEffect(() => onInside(stage === 'inside'), [stage, onInside]);

  const join = useMutation({
    mutationFn: async () => {
      const { id } = await ready();
      const { token, ice } = guest
        ? await guest.enter()
        : await postJson<Joining>(`/api/meetings/${id}/join`);
      // What was turned off before joining is turned on later as a new track of the device chosen.
      const made = new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: { deviceId: await own?.audio?.getDeviceId(false), ...sound },
        audioOutput: { deviceId: keptDevice('audiooutput')?.ideal },
        videoCaptureDefaults: {
          deviceId: await own?.video?.getDeviceId(false),
          resolution: VideoPresets.h720.resolution,
        },
      });
      made.on(RoomEvent.Disconnected, (reason) => {
        setStage(reason === DisconnectReason.CLIENT_INITIATED ? 'left' : 'dropped');
        setRoom(null);
      });
      await made.connect(signalling(), token, ice ? { rtcConfig: { iceServers: ice } } : {});
      for (const track of [own?.audio, own?.video]) {
        if (!track) continue;
        if (track.isMuted) track.stop();
        else await made.localParticipant.publishTrack(track);
      }
      return made;
    },
    onSuccess: (made) => {
      setRoom(made);
      setStage('inside');
    },
  });

  useEffect(() => () => void room?.disconnect(), [room]);
  useHeldRelease(room !== null);

  // A ring answered on another page lands here to be in the meeting at once; the mark is taken
  // off so that neither a reload nor the way back joins again.
  const location = useLocation();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const picked = useRef(false);
  useEffect(() => {
    if (!search.has('answered') || !own || picked.current) return;
    picked.current = true;
    navigate(location.pathname, { replace: true });
    join.mutate();
  }, [location, search, own, join, navigate]);

  if (stage === 'inside' && room)
    return guest ? (
      <Inside
        meeting={meeting}
        room={room}
        talk={guest.talk}
        guest
        guestKey={guest.key}
        look={look}
        shaping={shaping}
        notice={notice}
        onFailed={(error) => setNotice({ dropped: null, error })}
      />
    ) : (
      <MemberInside
        meeting={meeting}
        room={room}
        look={look}
        shaping={shaping}
        notice={notice}
        onFailed={(error) => setNotice({ dropped: null, error })}
      />
    );
  if (stage === 'left' || stage === 'dropped') {
    return (
      <Outside
        meeting={meeting.id}
        dropped={stage === 'dropped'}
        guest={!!guest}
        onJoin={async () => {
          const again = await taken(look.choices);
          setOwn(again);
          setStage('before');
        }}
      />
    );
  }
  return (
    <Before
      meeting={meeting}
      ready={ready}
      guest={guest}
      own={own}
      onOwn={setOwn}
      look={look}
      shaping={shaping}
      notice={notice}
      onFailed={(error) => setNotice({ dropped: null, error })}
      joining={join.isPending}
      failed={join.error}
      onJoin={() => join.mutate()}
      onCancel={() => {
        guest?.cancel();
        join.reset();
      }}
    />
  );
}

function Before({
  meeting,
  ready,
  guest,
  own,
  onOwn,
  look,
  shaping,
  notice,
  onFailed,
  joining,
  failed,
  onJoin,
  onCancel,
}: {
  meeting: Shown;
  ready: () => Promise<Shown>;
  guest?: Guesting;
  own: Own | null;
  onOwn: (own: Own) => void;
  look: Look;
  shaping: Shaping;
  notice: ShapingState;
  onFailed: (error: Error) => void;
  joining: boolean;
  failed: Error | null;
  onJoin: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const back = useBack();
  const reachable = useReachable();
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  const toggle = async (track: LocalAudioTrack | LocalVideoTrack | undefined) => {
    if (!track) return;
    await (track.isMuted ? track.unmute() : track.mute());
    redraw();
  };
  const choose = async (kind: Kind, device: string) => {
    const track = kind === 'videoinput' ? own?.video : kind === 'audioinput' ? own?.audio : null;
    await track?.setDeviceId(device);
    keepDevice(kind, device);
    if (own) onOwn({ ...own });
  };
  useEffect(() => shaping.follow(own?.video), [shaping, own?.video]);
  return (
    <div className="m-auto flex w-full max-w-xl flex-col gap-4 p-4">
      <h1 className="text-xl font-semibold">{meeting.title || t('meeting.untitled')}</h1>
      <div className="relative aspect-video overflow-hidden rounded-lg bg-panel">
        {own?.video && !own.video.isMuted ? (
          <TrackView track={own.video} mirrored />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted">
            {own ? t(own.video ? 'meeting.cameraIsOff' : 'meeting.noCamera') : t('tree.loading')}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 flex justify-center gap-2 p-3">
          <Switch
            on={!!own?.audio && !own.audio.isMuted}
            disabled={!own?.audio}
            onClick={() => void toggle(own?.audio)}
            onIcon={Mic}
            offIcon={MicOff}
            onLabel="meeting.micOff"
            offLabel="meeting.micOn"
          />
          <Switch
            on={!!own?.video && !own.video.isMuted}
            disabled={!own?.video}
            onClick={() => void toggle(own?.video)}
            onIcon={Video}
            offIcon={VideoOff}
            onLabel="meeting.cameraOff"
            offLabel="meeting.cameraOn"
          />
          {own && (
            <Devices
              active={(kind) =>
                kind === 'videoinput'
                  ? own.video?.mediaStreamTrack.getSettings().deviceId
                  : kind === 'audioinput'
                    ? own.audio?.mediaStreamTrack.getSettings().deviceId
                    : undefined
              }
              onChoose={(kind, device) => void choose(kind, device)}
              speakers={false}
              look={look}
              onFailed={onFailed}
            />
          )}
        </div>
      </div>
      <ShapingNotice state={notice} onRetry={() => shaping.retry()} />
      {own?.refused && <p className="text-sm text-danger">{t('meeting.refused')}</p>}
      {guest ? (
        <label className="flex flex-col gap-1 text-sm">
          {t('meeting.yourName')}
          <input
            value={guest.name}
            onChange={(event) => guest.onName(event.target.value)}
            maxLength={200}
            autoComplete="name"
            disabled={joining}
            className={field}
          />
        </label>
      ) : (
        <>
          <p className="text-sm text-muted">
            {meeting.present.length
              ? `${t('meeting.present')}: ${meeting.present.join(', ')}`
              : t('meeting.nobody')}
          </p>
          <AtDoor meeting={meeting.id} />
          {!meeting.planned && <Rings meeting={meeting.id} />}
          {meeting.id && <Recordings meeting={meeting.id} />}
        </>
      )}
      {guest?.waiting && <p role="status">{t('meeting.waiting')}</p>}
      {failed && (
        <p className="text-sm text-danger">
          {t('meeting.failed')}: {errorMessage(failed, t)}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {guest?.waiting ? (
          <button type="button" onClick={onCancel} className={button}>
            {t('tree.cancel')}
          </button>
        ) : (
          <button
            type="button"
            onClick={onJoin}
            disabled={!own || joining || (!!guest && !guest.name.trim()) || !reachable}
            title={reachable ? undefined : t('offline.needed')}
            className={primaryButton}
          >
            <Video size={16} aria-hidden />
            {t('meeting.join')}
          </button>
        )}
        {guest ? (
          <button type="button" onClick={guest.signIn} className="ml-auto text-sm underline">
            {t('meeting.signIn')}
          </button>
        ) : (
          <>
            {meeting.planned ? (
              <CopyLink link={meeting.link} />
            ) : (
              <AddPeople meeting={meeting} ready={ready} />
            )}
            <button type="button" onClick={back} className={`${button} ml-auto`}>
              {t('meeting.back')}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/** Back to the page the meeting was opened from, or to Today where it was opened by its link; a
    meeting's own window closes, the app it was opened from beside it. */
function useBack(): () => void {
  const navigate = useNavigate();
  return () => {
    if (isBeside()) window.close();
    else if ((window.history.state?.idx ?? 0) > 0) void navigate(-1);
    else void navigate('/');
  };
}

function Outside({
  meeting,
  dropped,
  guest,
  onJoin,
}: {
  meeting: string;
  dropped: boolean;
  guest: boolean;
  onJoin: () => Promise<void>;
}) {
  const { t } = useI18n();
  const back = useBack();
  const reachable = useReachable();
  return (
    <div className="m-auto flex max-w-md flex-col items-center gap-4 p-4 text-center">
      <p className={dropped ? 'text-danger' : ''}>
        {t(dropped ? 'meeting.dropped' : 'meeting.left')}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void onJoin()}
          disabled={!reachable}
          title={reachable ? undefined : t('offline.needed')}
          className={primaryButton}
        >
          {t('meeting.rejoin')}
        </button>
        {!guest && (
          <button type="button" onClick={back} className={button}>
            {t('meeting.back')}
          </button>
        )}
      </div>
      {!guest && <Recordings meeting={meeting} />}
    </div>
  );
}

/** A member's call, whose conversation they follow through the live channel, which a guest's
    page never opens. */
function MemberInside({
  meeting,
  room,
  ...shaped
}: {
  meeting: Shown;
  room: Room;
  look: Look;
  shaping: Shaping;
  notice: ShapingState;
  onFailed: (error: Error) => void;
}) {
  const talk = useMemberTalk(meeting.conversation);
  return <Inside meeting={meeting} room={room} talk={talk} guest={false} {...shaped} />;
}

function Inside({
  meeting,
  room,
  talk,
  guest,
  guestKey,
  look,
  shaping,
  notice,
  onFailed,
}: {
  meeting: Shown;
  room: Room;
  talk: Talk;
  guest: boolean;
  guestKey?: string | null;
  look: Look;
  shaping: Shaping;
  notice: ShapingState;
  onFailed: (error: Error) => void;
}) {
  const { t } = useI18n();
  const wide = useWide();
  const recording = useRecording(room, meeting.id, guest ? (guestKey ?? null) : undefined);
  const [talking, setTalking] = useState(false);
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  useEffect(() => {
    const redrawn = () => redraw();
    for (const event of REDRAWN) room.on(event, redrawn);
    return () => {
      for (const event of REDRAWN) room.off(event, redrawn);
    };
  }, [room]);

  const local = room.localParticipant;
  const camera = local.getTrackPublication(Track.Source.Camera)?.track as
    LocalVideoTrack | undefined;
  useEffect(() => shaping.follow(camera), [shaping, camera]);
  const everyone: Participant[] = [local, ...room.remoteParticipants.values()];
  const sharing = everyone.find((each) => each.isScreenShareEnabled);
  const shared = sharing?.getTrackPublication(Track.Source.ScreenShare);
  const switched = (enable: Promise<unknown>) =>
    void enable.catch((error: Error) => {
      if (error.name !== 'NotAllowedError') throw error;
    });
  const canShare = !!navigator.mediaDevices?.getDisplayMedia;
  const moving = useMutation({ mutationFn: toNextScreen });

  return (
    <>
      <header className="flex items-center gap-3 border-b border-line px-4 py-2">
        <h1 className="min-w-0 flex-1 truncate font-semibold">
          {meeting.title || t('meeting.untitled')}
        </h1>
        {recording.mark}
        <span className="flex items-center gap-1 text-sm text-muted" title={t('meeting.people')}>
          <Users size={16} aria-hidden />
          {everyone.length}
        </span>
        {hasScreens() && (
          <button
            type="button"
            onClick={() => moving.mutate()}
            title={t('meeting.nextScreen')}
            className={button}
          >
            <Monitor size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('meeting.nextScreen')}</span>
          </button>
        )}
        {!guest &&
          (meeting.planned ? <CopyLink link={meeting.link} /> : <AddPeople meeting={meeting} />)}
      </header>
      {recording.question}
      <ShapingNotice state={notice} onRetry={() => shaping.retry()} />
      {moving.error && (
        <p role="alert" className="bg-panel px-4 py-1 text-sm text-danger">
          {moving.error.name === 'NotAllowedError'
            ? t('meeting.screenRefused')
            : errorMessage(moving.error, t)}
        </p>
      )}
      {!guest && (
        <div className="flex flex-col gap-2 border-b border-line px-4 py-2 empty:hidden">
          <AtDoor meeting={meeting.id} />
          {!meeting.planned && <Rings meeting={meeting.id} />}
        </div>
      )}
      {room.state === ConnectionState.Reconnecting && (
        <p className="bg-panel px-4 py-1 text-sm text-danger">{t('meeting.reconnecting')}</p>
      )}
      {!room.canPlaybackAudio && (
        <div className="flex justify-center p-2">
          <button type="button" onClick={() => void room.startAudio()} className={primaryButton}>
            <Volume2 size={16} aria-hidden />
            {t('meeting.playAudio')}
          </button>
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <main
          className={`${talking && !wide ? 'hidden' : 'flex'} min-h-0 min-w-0 flex-1 gap-2 p-2 ${shared && wide ? 'flex-row' : 'flex-col'}`}
        >
          {shared?.track && (
            <div className="relative min-h-0 flex-[3] overflow-hidden rounded-lg bg-panel">
              {/* A screen shown on the screen it shares is shared again inside itself, without end. */}
              {sharing === local ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
                  <MonitorUp size={32} className="text-accent" aria-hidden />
                  <p>{t('meeting.presenting')}</p>
                  <p className="text-sm text-muted">{t('meeting.presentingHidden')}</p>
                </div>
              ) : (
                <>
                  <TrackView track={shared.track} contained />
                  <Label name={sharing ? named(sharing, t) : ''} />
                </>
              )}
            </div>
          )}
          <Tiles everyone={everyone} beside={!!shared} wide={wide} speakers={room.activeSpeakers} />
        </main>
        {talking && (
          <aside
            aria-label={t('chat.messages')}
            className="flex min-h-0 w-full flex-col px-3 pb-2 md:w-80 md:border-l md:border-line"
          >
            <Conversation talk={talk} />
          </aside>
        )}
      </div>
      {[...room.remoteParticipants.values()].map((each) => {
        const microphone = each.getTrackPublication(Track.Source.Microphone);
        return microphone?.track ? <Sound key={each.identity} publication={microphone} /> : null;
      })}
      <footer className="flex flex-wrap items-center justify-center gap-2 border-t border-line p-3">
        <Switch
          on={local.isMicrophoneEnabled}
          onClick={() => switched(local.setMicrophoneEnabled(!local.isMicrophoneEnabled))}
          onIcon={Mic}
          offIcon={MicOff}
          onLabel="meeting.micOff"
          offLabel="meeting.micOn"
        />
        <Switch
          on={local.isCameraEnabled}
          onClick={() => switched(local.setCameraEnabled(!local.isCameraEnabled))}
          onIcon={Video}
          offIcon={VideoOff}
          onLabel="meeting.cameraOff"
          offLabel="meeting.cameraOn"
        />
        {canShare && (
          <button
            type="button"
            onClick={() =>
              switched(
                local.setScreenShareEnabled(!local.isScreenShareEnabled, {
                  selfBrowserSurface: 'exclude',
                }),
              )
            }
            aria-pressed={local.isScreenShareEnabled}
            className={local.isScreenShareEnabled ? primaryButton : button}
          >
            <MonitorUp size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">
              {t(local.isScreenShareEnabled ? 'meeting.stopSharing' : 'meeting.share')}
            </span>
          </button>
        )}
        <Messages unread={talk.unread} talking={talking} onTalking={() => setTalking(!talking)} />
        <Devices
          active={(kind) => room.getActiveDevice(kind)}
          onChoose={(kind, device) => {
            keepDevice(kind, device);
            void room.switchActiveDevice(kind, device);
          }}
          speakers
          look={look}
          onFailed={onFailed}
        />
        {recording.control}
        <button type="button" onClick={() => void room.disconnect()} className={dangerButton}>
          <PhoneOff size={16} aria-hidden />
          {t('meeting.leave')}
        </button>
      </footer>
    </>
  );
}

function Messages({
  unread,
  talking,
  onTalking,
}: {
  unread: number;
  talking: boolean;
  onTalking: () => void;
}) {
  const { t, formatNumber } = useI18n();
  return (
    <button
      type="button"
      onClick={onTalking}
      aria-pressed={talking}
      className={`${talking ? primaryButton : button} relative`}
    >
      <MessageSquare size={16} aria-hidden />
      <span className="sr-only sm:not-sr-only">{t('chat.messages')}</span>
      {unread > 0 && !talking && (
        <span
          aria-label={t('chat.unread')}
          className="absolute -top-1.5 -right-1.5 min-w-4 rounded-full bg-accent px-1 text-center text-[0.625rem] leading-4 font-semibold text-on-accent tabular-nums"
        >
          {formatNumber(unread)}
        </span>
      )}
    </button>
  );
}

function isGuest(participant: Participant): boolean {
  return !!participant.metadata && JSON.parse(participant.metadata).guest === true;
}

function named(participant: Participant, t: (key: MessageKey) => string): string {
  const name = participant.name || participant.identity;
  if (participant.isLocal) return `${name} (${t('meeting.you')})`;
  return isGuest(participant) ? `${name} (${t('meeting.guest')})` : name;
}

function Tiles({
  everyone,
  beside,
  wide,
  speakers,
}: {
  everyone: Participant[];
  beside: boolean;
  wide: boolean;
  speakers: Participant[];
}) {
  const { t } = useI18n();
  const count = everyone.length;
  const columns = beside
    ? 1
    : wide
      ? count <= 1
        ? 1
        : count <= 4
          ? 2
          : count <= 9
            ? 3
            : 4
      : count <= 2
        ? 1
        : 2;
  const layout = beside
    ? wide
      ? 'flex w-56 shrink-0 flex-col gap-2 overflow-y-auto'
      : 'flex h-28 shrink-0 gap-2 overflow-x-auto'
    : 'grid min-h-0 flex-1 auto-rows-fr gap-2';
  return (
    <div
      className={layout}
      style={beside ? undefined : { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {everyone.map((participant) => {
        const camera = participant.getTrackPublication(Track.Source.Camera);
        const seen = camera?.track && !camera.isMuted ? camera.track : undefined;
        const name = named(participant, t);
        return (
          <div
            key={participant.identity}
            role="group"
            aria-label={name}
            className={`relative min-h-0 overflow-hidden rounded-lg bg-panel ${
              beside ? 'aspect-video shrink-0' : ''
            } ${speakers.includes(participant) ? 'ring-2 ring-accent' : ''}`}
          >
            {seen ? (
              <TrackView track={seen} mirrored={participant.isLocal} />
            ) : (
              <div className="flex h-full min-h-20 items-center justify-center">
                <span className="flex size-16 items-center justify-center rounded-full bg-selected text-xl font-semibold text-accent">
                  {initials(participant.name || participant.identity) || '?'}
                </span>
              </div>
            )}
            <Label name={name} muted={!participant.isMicrophoneEnabled} />
          </div>
        );
      })}
    </div>
  );
}

function Label({ name, muted }: { name: string; muted?: boolean }) {
  const { t } = useI18n();
  return (
    <span className="absolute bottom-2 left-2 flex max-w-[calc(100%-1rem)] items-center gap-1 rounded bg-surface/80 px-2 py-0.5 text-xs text-ink">
      {muted && <MicOff size={12} aria-label={t('meeting.muted')} />}
      <span className="truncate">{name}</span>
    </span>
  );
}

function TrackView({
  track,
  mirrored,
  contained,
}: {
  track: Track;
  mirrored?: boolean;
  contained?: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    track.attach(element);
    return () => {
      track.detach(element);
    };
  }, [track]);
  return (
    <video
      ref={ref}
      muted
      playsInline
      className={`size-full ${contained ? 'object-contain' : 'object-cover'} ${
        mirrored ? '-scale-x-100' : ''
      }`}
    />
  );
}

function Sound({ publication }: { publication: TrackPublication }) {
  const ref = useRef<HTMLAudioElement>(null);
  const track = publication.track;
  useEffect(() => {
    const element = ref.current;
    if (!element || !track) return;
    track.attach(element);
    return () => {
      track.detach(element);
    };
  }, [track]);
  return <audio ref={ref} />;
}

function Switch({
  on,
  disabled,
  onClick,
  onIcon: OnIcon,
  offIcon: OffIcon,
  onLabel,
  offLabel,
}: {
  on: boolean;
  disabled?: boolean;
  onClick: () => void;
  onIcon: typeof Mic;
  offIcon: typeof Mic;
  onLabel: MessageKey;
  offLabel: MessageKey;
}) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={t(on ? onLabel : offLabel)}
      title={t(on ? onLabel : offLabel)}
      className={on ? `${button} bg-surface` : dangerButton}
    >
      {on ? <OnIcon size={16} aria-hidden /> : <OffIcon size={16} aria-hidden />}
    </button>
  );
}

/** The devices to choose from. A browser names them only once the page may use them, so the
    menu waits for the own tracks and is left out while none is named. */
function Devices({
  active,
  onChoose,
  speakers,
  look,
  onFailed,
}: {
  active: (kind: Kind) => string | undefined;
  onChoose: (kind: Kind, device: string) => void;
  speakers: boolean;
  look: Look;
  onFailed: (error: Error) => void;
}) {
  const { t } = useI18n();
  const picker = useRef<HTMLInputElement>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  useEffect(() => {
    const read = () =>
      void navigator.mediaDevices
        .enumerateDevices()
        .then((found) => setDevices(found.filter((each) => each.deviceId)));
    read();
    navigator.mediaDevices.addEventListener('devicechange', read);
    return () => navigator.mediaDevices.removeEventListener('devicechange', read);
  }, []);
  const kinds = KINDS.filter(
    ({ kind }) =>
      (kind !== 'audiooutput' || speakers) && devices.some((each) => each.kind === kind),
  );
  if (kinds.length === 0) return null;
  return (
    <>
      <input
        ref={picker}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/avif"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) look.keepOwn(file).catch(onFailed);
        }}
      />
      <Menu
        align="start"
        trigger={
          <button
            type="button"
            aria-label={t('meeting.devices')}
            title={t('meeting.devices')}
            className={`${button} bg-surface`}
          >
            <Settings size={16} aria-hidden />
          </button>
        }
      >
        {kinds.map(({ kind, label, icon }) => (
          <MenuSub key={kind} icon={icon} label={t(label)}>
            <MenuChoices
              value={active(kind) ?? 'default'}
              choices={devices
                .filter((each) => each.kind === kind)
                .map((each, index) => ({
                  value: each.deviceId,
                  label: each.label || `${t(label)} ${index + 1}`,
                }))}
              onChange={(device) => onChoose(kind, device)}
            />
          </MenuSub>
        ))}
        <LookItems look={look} onPick={() => picker.current?.click()} />
      </Menu>
    </>
  );
}
