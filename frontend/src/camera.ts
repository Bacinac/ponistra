import {
  type BackgroundOptions,
  BackgroundTransformer,
  ProcessorWrapper,
  supportsBackgroundProcessors,
  type TrackTransformerDestroyOptions,
} from '@livekit/track-processors';
import { FaceDetector, FilesetResolver } from '@mediapipe/tasks-vision';
import type { AudioCaptureOptions, LocalAudioTrack, LocalVideoTrack } from 'livekit-client';
import { TrackEvent } from 'livekit-client';
import vision from 'virtual:vision';
import evening from './assets/backdrops/evening.jpg';
import paper from './assets/backdrops/paper.jpg';
import petrol from './assets/backdrops/petrol.jpg';
import sage from './assets/backdrops/sage.jpg';
import faceModel from './assets/models/blaze_face_short_range.tflite?url';
import segmenterModel from './assets/models/selfie_segmenter.tflite?url';

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

/** Every effect on the picture needs WebGL 2 and frames the page can read. */
export const SHAPEABLE = supportsBackgroundProcessors();

const BLUR = { soft: 6, strong: 18 };
// Over STRAINED frames after the first WARM ones, a frame taking BUDGET ms on average leaves the
// picture below 25 frames a second and the page's own thread full: the call itself stutters.
const BUDGET = 40;
const WARM = 30;
const STRAINED = 75;
const FACES_EVERY = 200;
const FACES_KEPT = 3000;
const LIGHT_EVERY = 500;
const WHOLE: View = { x: 0, y: 0, size: 1 };

/** The part of the picture shown, as fractions of its width and height: a square of the frame's
    own proportions, so that the picture keeps them. */
interface View {
  x: number;
  y: number;
  size: number;
}

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

/** Where the faces in the picture are framed: they fill about a third of its height, their middle
    a little above the picture's, never closer than half the picture. */
function framed(faces: { x: number; y: number; width: number; height: number }): View {
  const size = clamp(Math.max(faces.height * 3, faces.width * 1.8), 0.5, 1);
  return {
    x: clamp(faces.x + faces.width / 2 - size / 2, 0, 1 - size),
    y: clamp(faces.y + faces.height / 2 - size * 0.4, 0, 1 - size),
    size,
  };
}

/** The background segmenter of LiveKit's processors, with the picture framed on the faces and a
    dark one lit before it, and a watch on what each frame costs. */
class Shaped extends BackgroundTransformer {
  framing = false;
  light = false;
  private faces?: FaceDetector;
  private facesLoading?: Promise<void>;
  private stage?: OffscreenCanvas;
  private stageContext?: OffscreenCanvasRenderingContext2D;
  private probe?: OffscreenCanvasRenderingContext2D;
  private view = WHOLE;
  private aim = WHOLE;
  private facesAt = 0;
  private seenAt = 0;
  private lightAt = 0;
  private gain = 1;
  private wantedGain = 1;
  private frames = 0;
  private spent = 0;

  constructor(
    options: BackgroundOptions,
    private readonly strained: () => void,
    private readonly failed: (error: Error) => void,
  ) {
    super(options);
  }

  shape({ framing, light }: { framing: boolean; light: boolean }) {
    this.framing = framing;
    this.light = light;
    if (framing) this.loadFaces();
  }

  private loadFaces() {
    this.facesLoading ??= FilesetResolver.forVisionTasks(vision)
      .then((files) =>
        FaceDetector.createFromOptions(files, {
          baseOptions: { modelAssetPath: faceModel, delegate: 'CPU' },
          runningMode: 'VIDEO',
          minDetectionConfidence: 0.6,
        }),
      )
      .then((detector) => {
        this.faces = detector;
      })
      .catch((error: Error) => this.failed(error));
  }

  override async transform(frame: VideoFrame, controller: TransformStreamDefaultController) {
    const started = performance.now();
    const shaped = (this.framing || this.light) && !this.isDisabled ? this.shaped(frame) : frame;
    await super.transform(shaped, controller);
    this.measure(performance.now() - started);
  }

  private shaped(frame: VideoFrame): VideoFrame {
    const width = frame.displayWidth;
    const height = frame.displayHeight;
    if (!width || !height) return frame;
    if (!this.stage || this.stage.width !== width || this.stage.height !== height) {
      this.stage = new OffscreenCanvas(width, height);
      this.stageContext = this.stage.getContext('2d') ?? undefined;
    }
    const context = this.stageContext;
    if (!context) return frame;
    const now = performance.now();
    if (this.framing) this.follow(frame, now);
    else this.aim = WHOLE;
    const ease = (from: number, to: number) => from + (to - from) * 0.12;
    this.view = {
      x: ease(this.view.x, this.aim.x),
      y: ease(this.view.y, this.aim.y),
      size: ease(this.view.size, this.aim.size),
    };
    if (this.light && now - this.lightAt >= LIGHT_EVERY) {
      this.lightAt = now;
      this.wantedGain = this.lit(frame);
    }
    this.gain += ((this.light ? this.wantedGain : 1) - this.gain) * 0.1;
    context.filter =
      this.gain > 1.01
        ? `brightness(${this.gain.toFixed(3)}) contrast(1.06) saturate(1.06)`
        : 'none';
    context.drawImage(
      frame,
      this.view.x * width,
      this.view.y * height,
      this.view.size * width,
      this.view.size * height,
      0,
      0,
      width,
      height,
    );
    const shaped = new VideoFrame(this.stage, { timestamp: frame.timestamp });
    frame.close();
    return shaped;
  }

  /** Aims at the faces found five times a second, holding the aim while a face turns away for a
      moment and moving only where the faces moved enough to matter. */
  private follow(frame: VideoFrame, now: number) {
    if (!this.faces || now - this.facesAt < FACES_EVERY) return;
    this.facesAt = now;
    const found = this.faces
      .detectForVideo(frame, now)
      .detections.flatMap((each) => (each.boundingBox ? [each.boundingBox] : []));
    if (found.length === 0) {
      if (now - this.seenAt > FACES_KEPT) this.aim = WHOLE;
      return;
    }
    this.seenAt = now;
    const width = frame.displayWidth;
    const height = frame.displayHeight;
    const left = Math.min(...found.map((box) => box.originX));
    const top = Math.min(...found.map((box) => box.originY));
    const right = Math.max(...found.map((box) => box.originX + box.width));
    const bottom = Math.max(...found.map((box) => box.originY + box.height));
    const aim = framed({
      x: left / width,
      y: top / height,
      width: (right - left) / width,
      height: (bottom - top) / height,
    });
    const moved = Math.max(
      Math.abs(aim.x - this.aim.x),
      Math.abs(aim.y - this.aim.y),
      Math.abs(aim.size - this.aim.size),
    );
    if (moved > 0.04) this.aim = aim;
  }

  /** How much brighter the picture is drawn: a dark one up to twice, one lit enough not at all. */
  private lit(frame: VideoFrame): number {
    this.probe ??=
      new OffscreenCanvas(32, 18).getContext('2d', { willReadFrequently: true }) ?? undefined;
    if (!this.probe) return 1;
    this.probe.drawImage(frame, 0, 0, 32, 18);
    const { data } = this.probe.getImageData(0, 0, 32, 18);
    let sum = 0;
    for (let at = 0; at < data.length; at += 4)
      sum += 0.299 * data[at] + 0.587 * data[at + 1] + 0.114 * data[at + 2];
    const mean = sum / (data.length / 4) / 255;
    return mean < 0.4 ? clamp(0.45 / Math.max(mean, 0.05), 1, 2) : 1;
  }

  private measure(spent: number) {
    this.frames += 1;
    if (this.frames <= WARM) return;
    this.spent = this.frames === WARM + 1 ? spent : this.spent * 0.95 + spent * 0.05;
    if (this.frames > WARM + STRAINED && this.spent > BUDGET) {
      this.frames = 0;
      this.strained();
    }
  }

  override async destroy(options?: TrackTransformerDestroyOptions) {
    const faces = this.faces;
    this.faces = undefined;
    this.facesLoading = undefined;
    faces?.close();
    await super.destroy(options);
  }
}

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
    this.track = track;
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
    const wanted = SHAPEABLE && (background !== 'none' || framing || light);
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
    const transformer = new Shaped(
      { ...options, assetPaths: { tasksVisionFileSet: vision, modelAssetPath: segmenterModel } },
      () => this.strained(),
      (error) => this.told({ dropped: this.dropped, error }),
    );
    transformer.shape({ framing, light });
    this.shaped.set(track, transformer);
    await track.setProcessor(new ProcessorWrapper(transformer, 'ponistra-camera'));
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
