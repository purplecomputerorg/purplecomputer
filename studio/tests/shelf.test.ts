import { beforeEach, describe, expect, it } from "vitest";
import { buildPack, openPack } from "../src/pack";
import { artOf, removeFromPack, roomFileOf, shelf, shelfName, shelve, shelveDraft, unshelve, usedIn } from "../src/shelf";
import { draft, emptyDraft, replaceDraft, type RoomFile } from "../src/state";
import type { Picture } from "../src/photo";

const png = new Uint8Array([137, 80, 78, 71, 1, 2, 3]);
const room = (name: string, source: string) => ({ name, source, made: null, kept: true });
const art = (name: string, sourceUrl: string, more: Partial<Picture> = {}) => ({ name, sourceUrl, cells: [], ops: [], bitmap: null!, kept: true, ...more }) as Picture;

beforeEach(() => {
  shelf.length = 0;
  replaceDraft();
});

describe("the family's pictures", () => {
  it("keeps one of each picture, whether it comes back by id or as the very same photo", () => {
    const dog = shelve("data:image/png;base64,AAA", "Dog");
    expect(shelve("data:image/png;base64,AAA", "Another dog")).toBe(dog);
    expect(shelve("data:image/png;base64,BBB", "Dog", dog.id)).toBe(dog);
    expect(shelve("data:image/png;base64,CCC", "Dog").name).toBe("dog-2");
    expect(shelf).toHaveLength(2);
  });

  it("names a picture clear of one of ours the family made their own", () => {
    draft.pictures = [art("saturn", "/assets/saturn.jpg")];
    expect(shelfName("Saturn")).toBe("saturn-2");
  });

  it("ties a reopened pack's pictures to the shelf, one picture for Art and its rooms alike", () => {
    const d = emptyDraft();
    const file: RoomFile = { kind: "images", name: "dog", data: png, kept: true };
    d.pictures = [art("dog", "data:image/jpeg;base64,DOG"), art("starry-night", "/assets/starry-night.jpg")];
    d.roomFiles = [file, { kind: "sounds", name: "woof", data: png, kept: true }];
    shelveDraft(d);
    expect(shelf.map((s) => s.name)).toEqual(["dog", "dog-2"]);
    expect(d.pictures.map((p) => p.shelfId)).toEqual([shelf[0].id, undefined]);
    expect(file.shelfId).toBe(shelf[1].id);
    shelveDraft(d);
    expect(shelf).toHaveLength(2);
  });

  it("says where this pack uses a picture, and takes it out of the pack without taking it off the shelf", () => {
    const dog = shelve("data:image/png;base64,AAA", "Dog");
    draft.pictures = [art("dog", dog.src, { shelfId: dog.id })];
    draft.roomFiles = [{ kind: "images", name: "dog", data: png, kept: true, shelfId: dog.id }];
    draft.rooms = [room("memory", 'CARDS = ["🐱", "dog"]'), room("snake", "pass")];
    expect(usedIn(dog)).toEqual(["Art", "the Memory room"]);
    removeFromPack(dog);
    expect([artOf(dog), roomFileOf(dog), usedIn(dog)]).toEqual([undefined, undefined, []]);
    expect(shelf).toEqual([dog]);
    unshelve(dog);
    expect(shelf).toEqual([]);
  });

  it("finds a room picture on the shelf again after the pack is downloaded and reopened", async () => {
    const d = { ...emptyDraft(), rooms: [room("memory", "pass")], roomFiles: [{ kind: "images" as const, name: "dog", data: png, kept: true, shelfId: "shelf-1" }] };
    const back = await openPack((await buildPack(undefined, d)).blob);
    expect(back.roomFiles.map((f) => [f.name, f.shelfId])).toEqual([["dog", "shelf-1"]]);
  });
});
