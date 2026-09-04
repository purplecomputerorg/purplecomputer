// The app's draft, turned into the plain spec the SDK builds a pack from.
import { buildPack as build, packFilename as filename, type PackSpec } from "@sdk/pack";
import { previewPng } from "./photo";
import { draft, type Draft } from "./state";

export { manifest } from "@sdk/pack";

export async function packSpec(d: Draft = draft): Promise<PackSpec> {
  const pictures = await Promise.all(d.pictures.map(async (p) => ({ name: p.name, ops: p.ops, png: await previewPng(p.cells) })));
  return { ...d, pictures, rooms: d.rooms.map((r) => ({ program: r.program, blocks: r.blocks })) };
}

export async function buildPack(onProgress?: (msg: string) => void): Promise<Blob> {
  return build(await packSpec(), onProgress);
}

export const packFilename = () => filename(draft);
