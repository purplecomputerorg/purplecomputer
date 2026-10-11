import type { RoomSetup } from "../live/boot";

export interface Preview { element: HTMLElement; redraw?(): void; dispose(): void }

export interface View {
  title: string;
  // Purple doesn't use this part of the pack yet; the heading says so.
  soon?: boolean;
  editor: HTMLElement;
  // The real Purple, set up in this room. Takes the place of preview.
  live?: RoomSetup;
  // Built once per view and kept across edits, so whatever the parent typed into it stays.
  preview?: Preview;
  previewTitle?: string;
  caption?: string;
  // Called once the editor is in the document, for things that need a laid-out element (Blockly).
  mounted?: () => void;
  cleanup?: () => void;
}
