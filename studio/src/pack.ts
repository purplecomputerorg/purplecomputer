// The app's draft, turned into the plain spec the SDK builds a pack from, and a pack turned back into a draft.
import { buildPack as build, letterPath, packFilename as filename, phrasePath, pictureSourcePath, type PackSpec } from "@sdk/pack";
import { cellsToOps, type ArtPicture } from "@sdk/purple/art";
import { isCoreRanked } from "@sdk/purple/core";
import { gunzip, untar } from "@sdk/tar";
import { decodeWav } from "@sdk/wav";
import { dataUrl, onScreen, previewPng, sourceJpeg, type Crop } from "./photo";
import { draft, emptyDraft, type Draft, type Keepable } from "./state";

export { manifest } from "@sdk/pack";

// studio.json: what reopening needs beyond the files Purple reads. Clips are read back from the pack.
interface Saved extends Pick<PackSpec, "name" | "words" | "synonyms" | "ranked" | "instruments" | "rooms" | "theme"> {
  letters: string[];
  phrases: string[];
  pictures: { name: string; title?: string; cells: string[][]; crop?: Crop; painted?: ArtPicture }[];
}

// The download holds what the family added; Studio's own Purple also plays what they're trying.
export async function packSpec(d: Draft = draft, trying = false): Promise<PackSpec> {
  const ok = (x: Keepable) => trying || !!x.kept;
  const words = d.words.filter(ok);
  const added = d.pictures.filter(ok);
  // Only the download keeps the photos; Studio's own Purple never reopens a pack.
  const sources = trying ? [] : await Promise.all(added.map(sourceJpeg));
  const pictures = await Promise.all(added.map(async (p, i) => ({ name: p.name, title: p.title, ...onScreen(p), png: await previewPng(onScreen(p)), source: sources[i]?.jpg })));
  // A family's own words come first in autocomplete, after the words Purple already ranks.
  const ranked = [...new Set([...d.ranked, ...words.map((w) => w.word).filter((w) => !isCoreRanked(w))])];
  const letters = Object.fromEntries(Object.entries(d.letters).filter(([, l]) => ok(l)).map(([k, l]) => [k, l.clip]));
  const phrases = d.phrases.filter(ok);
  const synonyms = d.synonyms.filter(ok);
  const instruments = d.instruments.filter(ok);
  const rooms = d.rooms.filter(ok).map((r) => ({ name: r.name, source: r.source, blocks: r.blocks }));
  const theme = ok(d.colors) ? d.theme : null;
  const studio: Saved = {
    name: d.name, words, synonyms, ranked: d.ranked, instruments, rooms, theme,
    letters: Object.keys(letters), phrases: phrases.map((p) => p.text),
    pictures: added.map(({ name, title, cells, painted }, i) => ({ name, title, cells, painted, crop: sources[i]?.crop })),
  };
  return { id: d.id, name: d.name, pictures, words, ranked, letters, phrases, synonyms, instruments, rooms, theme, studio };
}

export async function buildPack(onProgress?: (msg: string) => void, d: Draft = draft, trying = false): Promise<Blob> {
  return build(await packSpec(d, trying), onProgress);
}

export const packFilename = () => filename(draft);

// A downloaded Purple Pack, back as the draft it was made from, everything in it added.
export async function openPack(file: Blob): Promise<Draft> {
  const files = new Map(untar(await gunzip(new Uint8Array(await file.arrayBuffer()))).map((e) => [e.path, e.data]));
  const read = (path: string) => {
    const data = files.get(path);
    if (!data) throw new Error(`${path} is missing`);
    return data;
  };
  const readJson = (path: string) => JSON.parse(new TextDecoder().decode(read(path)));
  const image = (path: string, type: string) => new Blob([read(path) as BlobPart], { type });
  const s: Saved = readJson("studio.json");
  const kept = <T extends object>(x: T) => ({ ...x, kept: true });
  return {
    ...emptyDraft(),
    id: readJson("manifest.json").id,
    name: s.name,
    words: s.words.map(kept),
    synonyms: s.synonyms.map(kept),
    ranked: s.ranked,
    instruments: s.instruments.map(kept),
    rooms: s.rooms.map((r) => kept({ ...r, blocks: r.blocks ?? null, template: null })),
    theme: s.theme,
    colors: s.theme ? { kept: true } : {},
    letters: Object.fromEntries(s.letters.map((k) => [k, kept({ clip: decodeWav(read(letterPath(k))) })])),
    phrases: s.phrases.map((text) => kept({ text, clip: decodeWav(read(phrasePath(text))) })),
    pictures: await Promise.all(s.pictures.map(async (p) => {
      const photo = image(pictureSourcePath(p.name), "image/jpeg");
      return kept({ ...p, ops: cellsToOps(p.cells), sourceUrl: await dataUrl(photo), bitmap: await createImageBitmap(photo) });
    })),
  };
}
