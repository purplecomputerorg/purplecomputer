// Browser audio: decoding, resampling, playback, and the microphone. The pure clip
// helpers live in the SDK and are re-exported here for the UI.
import { CLIP_SAMPLE_RATE } from "@sdk/purple/sounds";
import type { Clip } from "@sdk/wav";

export { encodeWav, normalize, peak, tidy, type Clip } from "@sdk/wav";

export async function decodeToClip(blob: Blob, rate = CLIP_SAMPLE_RATE): Promise<Clip> {
  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  await ctx.close();
  return renderClip(decoded, rate, 1);
}

// Resamples to mono at `rate`; `playbackRate` above 1 raises pitch and shortens the clip, like a sampler.
export async function renderClip(source: AudioBuffer, rate: number, playbackRate: number): Promise<Clip> {
  const length = Math.ceil((source.duration / playbackRate) * rate) + 1;
  const off = new OfflineAudioContext(1, length, rate);
  const node = new AudioBufferSourceNode(off, { buffer: source, playbackRate });
  node.connect(off.destination);
  node.start();
  const out = await off.startRendering();
  return { samples: out.getChannelData(0).slice(), rate };
}

export function clipToBuffer({ samples, rate }: Clip): AudioBuffer {
  const buffer = new AudioBuffer({ length: samples.length, sampleRate: rate, numberOfChannels: 1 });
  buffer.getChannelData(0).set(samples);
  return buffer;
}

let playCtx: AudioContext | null = null;

export function audioContext(): AudioContext {
  playCtx ??= new AudioContext();
  return playCtx;
}

export function play(clip: Clip): void {
  playBuffer(clipToBuffer(clip));
}

export function playBuffer(buffer: AudioBuffer): void {
  const ctx = audioContext();
  const node = new AudioBufferSourceNode(ctx, { buffer });
  node.connect(ctx.destination);
  node.start();
}

export class Recorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  get active(): boolean {
    return this.recorder?.state === "recording";
  }

  async start(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.recorder = new MediaRecorder(stream);
    this.recorder.ondataavailable = (e) => this.chunks.push(e.data);
    this.recorder.start();
  }

  stop(): Promise<Blob> {
    return new Promise((resolve) => {
      const rec = this.recorder!;
      rec.onstop = () => {
        rec.stream.getTracks().forEach((t) => t.stop());
        resolve(new Blob(this.chunks, { type: rec.mimeType }));
      };
      rec.stop();
    });
  }
}
