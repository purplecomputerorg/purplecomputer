// The app's draft, turned into the plain spec the SDK builds a pack from.
import { buildPack as build, packFilename as filename, type PackSpec } from "@sdk/pack";
import { isCoreRanked } from "@sdk/purple/core";
import { previewPng } from "./photo";
import { draft, type Draft, type Keepable } from "./state";

export { manifest } from "@sdk/pack";

// The download holds what the family added; Studio's own Purple also plays what they're trying.
export async function packSpec(d: Draft = draft, trying = false): Promise<PackSpec> {
  const ok = (x: Keepable) => trying || !!x.kept;
  const words = d.words.filter(ok);
  const pictures = await Promise.all(d.pictures.filter(ok).map(async (p) => ({ name: p.name, title: p.title, ops: p.ops, png: await previewPng(p.cells) })));
  // A family's own words come first in autocomplete, after the words Purple already ranks.
  const ranked = [...new Set([...d.ranked, ...words.map((w) => w.word).filter((w) => !isCoreRanked(w))])];
  return {
    name: d.name,
    pictures,
    words,
    ranked,
    letters: Object.fromEntries(Object.entries(d.letters).filter(([, l]) => ok(l)).map(([k, l]) => [k, l.clip])),
    phrases: d.phrases.filter(ok),
    synonyms: d.synonyms.filter(ok),
    instruments: d.instruments.filter(ok),
    rooms: d.rooms.filter(ok).map((r) => ({ name: r.name, source: r.source, blocks: r.blocks })),
    theme: ok(d.colors) ? d.theme : null,
  };
}

export async function buildPack(onProgress?: (msg: string) => void, d: Draft = draft, trying = false): Promise<Blob> {
  return build(await packSpec(d, trying), onProgress);
}

export const packFilename = () => filename(draft);
