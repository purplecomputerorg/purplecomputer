// The draft kept in this browser, so a reload or a closed tab loses nothing. Best effort only: Safari clears it
// after a week away, which is why the downloaded Purple Pack, reopened with openPack, is the copy that lasts.
import type { Shelved } from "./shelf";
import { draft, madeOf, type Draft, type Made, type RoomDraft } from "./state";

const KEY = "draft";
// The family's pictures, kept apart from any one draft.
const SHELF = "shelf";

function store<T>(mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open("purple-studio", 1);
    open.onupgradeneeded = () => open.result.createObjectStore("drafts");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const req = op(open.result.transaction("drafts", mode).objectStore("drafts"));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    };
  });
}

// Rooms saved before rules: a form room keeps its form, and a blocks room keeps its Python.
type OldRoom = RoomDraft & { template?: Made | null };
const upgrade = (d: Draft | undefined) => d && { ...d, rooms: d.rooms.map(({ template, ...r }: OldRoom) => ({ ...r, made: madeOf(r.made ?? template) })) };

export const recall = (): Promise<Draft | undefined> => store<Draft | undefined>("readonly", (s) => s.get(KEY)).then(upgrade).catch(() => undefined);

let pending: ReturnType<typeof setTimeout> | undefined;
export function remember() {
  clearTimeout(pending);
  pending = setTimeout(() => store("readwrite", (s) => s.put(draft, KEY)).catch(() => {}), 300);
}

export const recallShelf = (): Promise<Shelved[]> => store<Shelved[] | undefined>("readonly", (s) => s.get(SHELF)).then((x) => x ?? []).catch(() => []);
export const rememberShelf = (items: Shelved[]) => store("readwrite", (s) => s.put(items, SHELF)).catch(() => {});
