// The words as Purple would say them, after Purple's own speech filter ("" when it won't say them).
// live.ts is loaded here, not imported at the top: it needs a page, and it imports the room voice.
export const speakable = async (text: string) => (await import("./ui/live")).liveScreen().filter(text);
