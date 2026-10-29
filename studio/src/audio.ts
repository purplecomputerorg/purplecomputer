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

// Slower at the same pitch, by WSOLA: each 40 ms frame is taken from near its place in the input, nudged
// up to 10 ms to where it best continues the frame before, and the frames overlap by half.
export function stretch({ samples, rate }: Clip, tempo: number): Clip {
  const n = Math.round(rate * 0.02) * 2, hop = n / 2, tol = Math.round(rate * 0.01);
  const window = Float32Array.from({ length: n }, (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / n));
  const at = (i: number) => samples[i] ?? 0;
  const length = Math.round(samples.length / tempo);
  const out = new Float32Array(length + n);
  for (let k = 0, prev = 0; k * hop < length; k++) {
    const nominal = Math.round(k * hop * tempo);
    let best = nominal;
    for (let d = -tol, score = -Infinity; k > 0 && d <= tol; d++) {
      let s = 0;
      for (let i = 0; i < n; i += 2) s += at(prev + hop + i) * at(nominal + d + i);
      if (s > score) [score, best] = [s, nominal + d];
    }
    for (let i = 0; i < n; i++) out[k * hop + i] += at(best + i) * window[i];
    prev = best;
  }
  return { samples: out.slice(0, length), rate };
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

export function playBuffer(buffer: AudioBuffer, volume = 1): void {
  const ctx = audioContext();
  const node = new AudioBufferSourceNode(ctx, { buffer });
  node.connect(new GainNode(ctx, { gain: volume })).connect(ctx.destination);
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
