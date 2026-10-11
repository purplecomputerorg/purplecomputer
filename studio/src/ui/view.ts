import type { RoomSetup } from "../live/boot";

// press: a key tapped on the pretend laptop keyboard.
// focus: give it the computer's keyboard, as clicking it does.
export interface Preview { element: HTMLElement; redraw?(): void; press?(key: string): void; focus?(): void; dispose(): void }

export interface View {
  title: string;
  editor: HTMLElement;
  // The real Purple, set up in this room. Takes the place of preview.
  live?: RoomSetup;
  // Built once per view and kept across edits, so whatever the parent typed into it stays.
  preview?: Preview;
  // The few big keys a phone shows for this page's room; main.ts has some for every room.
  keys?: () => string[];
  previewTitle?: string;
  caption?: string;
  // Called once the editor is in the document, for things that need a laid-out element (Blockly).
  mounted?: () => void;
  cleanup?: () => void;
}
