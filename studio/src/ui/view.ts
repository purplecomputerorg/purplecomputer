// What every editor hands the shell: the editor pane, and a stage renderer the shell re-runs on change.
export interface View {
  title: string;
  path?: string;
  tag?: "real" | "proposed";
  editor: HTMLElement;
  stage: () => Node | null;
  stageTitle?: string;
  caption?: string;
  cleanup?: () => void;
}
