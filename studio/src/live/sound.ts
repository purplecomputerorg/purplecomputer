// Purple's sounds in the browser: pygame's mixer as browser.py's stand-in uses it, played by Web Audio,
// so the browser decodes them and Python's thread never mixes. A sound is a file's bytes, or the URL of a
// core sound (purple.zip holds those as empty files; studio_bundle.py serves them beside it).

// A sound still loading this long after it was played is skipped rather than heard late.
const LATE_MS = 500;
const ctx = new AudioContext();
const files = new Map<string, Promise<ArrayBuffer | null>>();
const sounds = new Map<number, { buffer: Promise<AudioBuffer | null>; length: number }>();
const channels = new Map<number, { sound: number; gain: GainNode; source?: AudioBufferSourceNode }>();
let lastChannel = 0;
let toWarm: string[] = [];

const fetchFile = (url: string) => {
  if (!files.has(url)) files.set(url, fetch(new URL(url, document.baseURI)).then((r) => (r.ok ? r.arrayBuffer() : null), () => null));
  return files.get(url)!;
};

function end(id: number): void {
  const ch = channels.get(id);
  channels.delete(id);
  try { ch?.source?.stop(); } catch { /* never started */ }
  ch?.gain.disconnect();
}

export const warmSounds = () => toWarm.forEach(fetchFile);

export const purpleSound = {
  load(id: number, from: string | Uint8Array): void {
    const bytes = typeof from === "string" ? fetchFile(from) : Promise.resolve(from.slice().buffer);
    const sound = { length: 0, buffer: bytes.then((b) => (b ? ctx.decodeAudioData(b.slice(0)) : null)).catch(() => null) };
    void sound.buffer.then((b) => (sound.length = b?.duration ?? 0));
    sounds.set(id, sound);
  },
  drop: (id: number) => void sounds.delete(id),
  // The core sounds, fetched once Purple is up (warmSounds), so the first note in a room isn't waiting on the network.
  warm: (urls: string[]) => void (toWarm = urls),
  play(id: number, volume: number): number {
    const channel = ++lastChannel;
    const gain = new GainNode(ctx, { gain: volume });
    gain.connect(ctx.destination);
    channels.set(channel, { sound: id, gain });
    const asked = performance.now();
    void (sounds.get(id)?.buffer ?? Promise.resolve(null)).then((buffer) => {
      const ch = channels.get(channel);
      if (!ch) return;
      if (!buffer || performance.now() - asked > LATE_MS) return end(channel);
      ch.source = new AudioBufferSourceNode(ctx, { buffer });
      ch.source.onended = () => end(channel);
      ch.source.connect(gain);
      ch.source.start();
    });
    void ctx.resume();
    return channel;
  },
  busy: (channel: number) => channels.has(channel),
  anyBusy: () => channels.size > 0,
  volume: (channel: number, v: number) => void (channels.get(channel)?.gain.gain.setValueAtTime(v, ctx.currentTime)),
  end,
  stopSound: (id: number) => [...channels].forEach(([channel, ch]) => ch.sound === id && end(channel)),
  stopAll: () => [...channels.keys()].forEach(end),
  length: (id: number) => sounds.get(id)?.length ?? 0,
};
