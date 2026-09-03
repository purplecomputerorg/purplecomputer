import { CLIP_SAMPLE_RATE } from "./purple/sounds";

export interface Clip { samples: Float32Array; rate: number }

export function encodeWav({ samples, rate }: Clip): Uint8Array {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const ascii = (offset: number, s: string) => [...s].forEach((c, i) => v.setUint8(offset + i, c.charCodeAt(0)));
  ascii(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  ascii(36, "data");
  v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Uint8Array(buf);
}

// Mirrors tts.postprocess_samples: trim below -40 dB with a little air on each side, 10 ms fades.
export function tidy({ samples, rate }: Clip, thresholdDb = -40, fadeMs = 10): Clip {
  const threshold = 10 ** (thresholdDb / 20);
  let start = samples.findIndex((s) => Math.abs(s) > threshold);
  if (start < 0) return { samples: new Float32Array(0), rate };
  let end = samples.length - 1;
  while (end > start && Math.abs(samples[end]) <= threshold) end--;
  start = Math.max(0, start - Math.floor(rate * 0.01));
  end = Math.min(samples.length, end + Math.floor(rate * 0.02));
  const out = samples.slice(start, end);
  const fade = Math.min(Math.floor((rate * fadeMs) / 1000), Math.floor(out.length / 2));
  for (let i = 0; i < fade; i++) {
    out[i] *= i / fade;
    out[out.length - 1 - i] *= i / fade;
  }
  return { samples: out, rate };
}

export function peak(samples: Float32Array): number {
  let p = 0;
  for (const s of samples) p = Math.max(p, Math.abs(s));
  return p;
}

export function normalize({ samples, rate }: Clip, target = 0.9): Clip {
  const p = peak(samples);
  return { samples: p > 0 ? samples.map((s) => (s / p) * target) : samples, rate };
}

// Browser-only helpers below.

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

export function play(clip: Clip): void {
  playCtx ??= new AudioContext();
  const node = new AudioBufferSourceNode(playCtx, { buffer: clipToBuffer(clip) });
  node.connect(playCtx.destination);
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
