import type { RoomSetup } from "../live/boot";

export interface View {
  title: string;
  // The list page this one came from: [href, label].
  back?: [string, string];
  editor: HTMLElement;
  // The real Purple, set up in this room.
  live?: RoomSetup;
  // The few big keys a phone shows for this page's room; main.ts has some for every room.
  keys?: () => string[];
  previewTitle?: string;
  caption?: string;
  // Called once the editor is in the document, for things that need a laid-out element (Blockly).
  mounted?: () => void;
  cleanup?: () => void;
  // What the topbar's Download button does while this page is open, instead of linking here.
  download?: () => void;
}
