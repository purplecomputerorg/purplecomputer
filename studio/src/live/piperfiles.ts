// Where Studio's Purple finds its voice: served under voice/ by scripts/studio_bundle.py, with Purple's
// settings from export.json.
import exported from "@sdk/purple/export.json";

export const { speaker: SPEAKER, scales: SCALES, word_gap: WORD_GAP, espeak_data: ESPEAK_DATA } = exported.voice.piper;
export const MODEL = `${exported.voice.piper.model}.onnx`;
export const CACHE = "purple-voice-1";
