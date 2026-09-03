import { clipToBuffer, encodeWav, renderClip } from "./audio";
import { previewPng } from "./photo";
import { generateRowGradient, ASDF_ROW, QWERTY_ROW, ZXCV_ROW } from "./purple/art";
import { CLIP_SAMPLE_RATE, SAMPLE_PITCHES, voiceClipFilename } from "./purple/sounds";
import { draft, packId, type Draft } from "./state";
import { gzip, tar, type TarEntry } from "./tar";

const enc = new TextEncoder();
const text = (path: string, body: string): TarEntry => ({ path, data: enc.encode(body) });
const json = (path: string, value: unknown) => text(path, JSON.stringify(value, null, 2) + "\n");

// The real, loader-read part of the pack: manifest plus the emoji type's three files.
export function manifest(d: Draft = draft) {
  return {
    id: packId(d),
    name: d.familyName ? `${d.familyName}${/s$/i.test(d.familyName) ? "'" : "'s"} Purple` : "Our Purple",
    version: "1.0.0",
    type: "emoji",
    description: "Made with Purple Studio.",
  };
}

export function emojiEntries(d: Draft = draft): TarEntry[] {
  const out: TarEntry[] = [];
  if (d.words.length) out.push(json("content/emoji.json", Object.fromEntries(d.words.map((w) => [w.word, w.emoji]))));
  if (d.synonyms.length) out.push(json("content/synonyms.json", Object.fromEntries(d.synonyms.map((s) => [s.alias, s.word]))));
  if (d.ranked.length) out.push(text("content/rankings.txt", d.ranked.join("\n") + "\n"));
  return out;
}

export function themeJson(d: Draft = draft) {
  const t = d.theme!;
  return {
    background: t.background,
    surface: t.surface,
    keys: {
      ...generateRowGradient(t.hues.qwerty, QWERTY_ROW),
      ...generateRowGradient(t.hues.asdf, ASDF_ROW),
      ...generateRowGradient(t.hues.zxcv, ZXCV_ROW),
    },
  };
}

export async function buildEntries(d: Draft = draft, onProgress?: (msg: string) => void): Promise<TarEntry[]> {
  const entries: TarEntry[] = [json("manifest.json", manifest(d)), ...emojiEntries(d)];

  for (const [key, clip] of Object.entries(d.letters)) entries.push({ path: `content/letters/${key}.wav`, data: encodeWav(clip) });
  for (const p of d.phrases) entries.push({ path: `content/voice/${voiceClipFilename(p.text)}`, data: encodeWav(p.clip) });

  for (const pic of d.pictures) {
    onProgress?.(`Saving ${pic.name}`);
    entries.push(json(`content/pictures/${pic.name}.json`, { name: pic.name, ops: pic.ops }));
    entries.push({ path: `content/pictures/${pic.name}.png`, data: await previewPng(pic.cells) });
  }

  if (d.instrument) {
    const { name, source, sourceFreq } = d.instrument;
    const buffer = clipToBuffer(source);
    for (const pitch of SAMPLE_PITCHES) {
      onProgress?.(`Tuning ${name}: ${pitch.note}${pitch.octave}`);
      const clip = await renderClip(buffer, CLIP_SAMPLE_RATE, pitch.freq / sourceFreq);
      entries.push({ path: `content/${name}/${pitch.file}.wav`, data: encodeWav(clip) });
    }
  }

  if (d.theme) entries.push(json("content/theme.json", themeJson(d)));
  return entries;
}

export async function buildPack(onProgress?: (msg: string) => void): Promise<Blob> {
  const entries = await buildEntries(draft, onProgress);
  onProgress?.("Packing");
  return new Blob([(await gzip(tar(entries))) as BlobPart], { type: "application/gzip" });
}

export const packFilename = () => `${packId()}.purplepack`;
