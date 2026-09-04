export interface View {
  title: string;
  path?: string;
  // "real": Purple reads this today. "proposed": written into the pack, read by nothing yet.
  tag?: "real" | "proposed";
  editor: HTMLElement;
  stage: () => HTMLElement | null;
  stageTitle?: string;
  caption?: string;
  // Called once the editor is in the document, for things that need a laid-out element (Blockly).
  mounted?: () => void;
  cleanup?: () => void;
}
