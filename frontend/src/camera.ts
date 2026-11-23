import type { BackgroundOptions } from '@livekit/track-processors';
import type { AudioCaptureOptions, LocalAudioTrack, LocalVideoTrack } from 'livekit-client';
import { TrackEvent } from 'livekit-client';
import evening from './assets/backdrops/evening.jpg';
import paper from './assets/backdrops/paper.jpg';
import petrol from './assets/backdrops/petrol.jpg';
import sage from './assets/backdrops/sage.jpg';
import type { Shaped } from './shaped';

export const BACKDROPS = { petrol, sage, paper, evening } as const;
export type Backdrop = keyof typeof BACKDROPS;
export type Background = 'none' | 'soft' | 'strong' | Backdrop | 'own';

/** What a call does with the camera and the microphone (S2-9), as the account keeps it. */
export interface CallChoices {
  background: Background;
  framing: boolean;
  light: boolean;
  noise: boolean;
  echo: boolean;
  gain: boolean;
}

export const UNCHOSEN: CallChoices = {
  background: 'none',
  framing: false,
  light: false,
  noise: true,
  echo: true,
  gain: true,
};

/** What the camera's processing had to give up on a device that could not keep up with it. */
export type Dropped = 'background' | 'all';

let processing: Promise<typeof import('./shaped')> | undefined;

/** MediaPipe and LiveKit's processors, loaded once the camera's picture is to be shaped. */
const processed = () => (processing ??= import('./shaped'));

/** Whether this browser can shape the camera's picture at all. */
export const shapeable = () => processed().then(({ SHAPEABLE }) => SHAPEABLE);

const BLUR = { soft: 16, strong: 48 };

function backgroundOf(background: Background, own: string | null): BackgroundOptions {
  if (background === 'soft' || background === 'strong')
    return { blurRadius: BLUR[background], imagePath: undefined, backgroundDisabled: false };
  const image = background === 'own' ? own : background === 'none' ? null : BACKDROPS[background];
  return image
    ? { imagePath: image, blurRadius: undefined, backgroundDisabled: false }
    : { imagePath: undefined, blurRadius: undefined, backgroundDisabled: true };
}

export interface ShapingState {
  dropped: Dropped | null;
  error: Error | null;
}

/** The camera's processing in one call, following its camera from track to track: before joining,
    in the call, and after the camera is turned on again as a new track. One processor stands on a
    track at a time, made anew for each. */
export class Shaping {
  private track?: LocalVideoTrack;
  private choices: CallChoices;
  private own: string | null;
  private dropped: Dropped | null = null;
  private shaped = new WeakMap<LocalVideoTrack, Shaped>();
  private queue = Promise.resolve();
  private readonly again = () => this.apply();

  constructor(
    choices: CallChoices,
    own: string | null,
    private readonly told: (state: ShapingState) => void,
  ) {
    this.choices = choices;
    this.own = own;
  }

  follow(track: LocalVideoTrack | undefined) {
    if (track === this.track) return;
    this.track?.off(TrackEvent.Unmuted, this.again);
    this.track = track;
    track?.on(TrackEvent.Unmuted, this.again);
    this.apply();
  }

  choose(choices: CallChoices, own: string | null) {
    this.choices = choices;
    this.own = own;
    this.apply();
  }

  /** Tries again what the device gave up. */
  retry() {
    this.dropped = null;
    this.told({ dropped: null, error: null });
    this.apply();
  }

  private apply() {
    this.queue = this.queue.then(() =>
      this.applied().catch((error: Error) => this.told({ dropped: this.dropped, error })),
    );
  }

  private async applied() {
    const track = this.track;
    if (!track) return;
    const background = this.dropped ? 'none' : this.choices.background;
    const framing = this.dropped !== 'all' && this.choices.framing;
    const light = this.dropped !== 'all' && this.choices.light;
    const wanted = (background !== 'none' || framing || light) && (await processed()).SHAPEABLE;
    const current = track.getProcessor() ? this.shaped.get(track) : undefined;
    if (!wanted) {
      if (track.getProcessor()) await track.stopProcessor();
      return;
    }
    const options = backgroundOf(background, this.own);
    if (current) {
      current.shape({ framing, light });
      await current.update(options);
      return;
    }
    // A camera turned off has ended its track; turned on again, it is shaped as it unmutes.
    if (track.mediaStreamTrack.readyState === 'ended') return;
    const { shapedOn } = await processed();
    const { transformer, processor } = shapedOn(
      options,
      () => this.strained(),
      (error) => this.told({ dropped: this.dropped, error }),
    );
    transformer.shape({ framing, light });
    this.shaped.set(track, transformer);
    await track.setProcessor(processor);
  }

  /** The background goes first, as it costs the most; framing and light after it. */
  private strained() {
    const background = this.dropped ? 'none' : this.choices.background;
    this.dropped = background !== 'none' ? 'background' : 'all';
    this.told({ dropped: this.dropped, error: null });
    this.apply();
  }
}

/** The microphone's constraints for the browser's own processing of the sound. */
export function soundOf(choices: CallChoices): AudioCaptureOptions {
  return {
    noiseSuppression: choices.noise,
    echoCancellation: choices.echo,
    autoGainControl: choices.gain,
  };
}

const pending = new WeakMap<LocalAudioTrack, AudioCaptureOptions>();

/** Gives the microphone what the user chose of the sound's processing. The browser applies it
    only to a track taken anew, and a muted one would come back live, so a muted microphone takes
    it as it is turned on again. */
export async function resound(track: LocalAudioTrack, choices: CallChoices) {
  const deviceId = track.mediaStreamTrack.getSettings().deviceId;
  const options = { ...soundOf(choices), deviceId: deviceId ? { ideal: deviceId } : undefined };
  if (!track.isMuted) return track.restartTrack(options);
  if (!pending.has(track))
    track.once(TrackEvent.Unmuted, () => {
      const waiting = pending.get(track);
      pending.delete(track);
      if (waiting) void track.restartTrack(waiting);
    });
  pending.set(track, options);
}
