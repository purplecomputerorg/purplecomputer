// Renders some of an instrument's notes as WAV files for notes.ts.
import { SYNTH_RATE, renderNote, type BaseName, type Params } from "@sdk/purple/synth";
import { encodeWav } from "@sdk/wav";

export interface NotesJob { id: number; base: BaseName; params: Params; freqs: number[] }

onmessage = ({ data: { id, base, params, freqs } }: MessageEvent<NotesJob>) => {
  const wavs = freqs.map((f) => encodeWav({ samples: renderNote(base, params, f), rate: SYNTH_RATE }));
  postMessage({ id, wavs }, { transfer: wavs.map((w) => w.buffer) });
};
