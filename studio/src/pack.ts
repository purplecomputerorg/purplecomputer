// The app's draft, turned into the plain spec the SDK builds a pack from.
import { buildPack as build, packFilename as filename, type PackSpec } from "@sdk/pack";
import { isCoreRanked } from "@sdk/purple/core";
import { previewPng } from "./photo";
import { draft, type Draft } from "./state";

export { manifest } from "@sdk/pack";

export async function packSpec(d: Draft = draft): Promise<PackSpec> {
  const pictures = await Promise.all(d.pictures.map(async (p) => ({ name: p.name, title: p.title, ops: p.ops, png: await previewPng(p.cells) })));
  // A family's own words come first in autocomplete, after the words Purple already ranks.
  const ranked = [...new Set([...d.ranked, ...d.words.map((w) => w.word).filter((w) => !isCoreRanked(w))])];
  return { ...d, pictures, ranked, rooms: d.rooms.map((r) => ({ name: r.name, source: r.source, blocks: r.blocks })) };
}

export async function buildPack(onProgress?: (msg: string) => void, d: Draft = draft): Promise<Blob> {
  return build(await packSpec(d), onProgress);
}

export const packFilename = () => filename(draft);
