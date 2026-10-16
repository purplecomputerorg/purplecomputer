"""Speech worker process. Loads the Piper voice once, warms it, then answers one
request per stdin line ("<wav path>\\t<prepared text>[\\t<model>]") with ok or fail.
A language pack's model loads on its first request and stays loaded.

Building the ONNX session holds the GIL for seconds, so it happens here instead
of in the UI process. Exits on stdin EOF, so it dies with the app."""

import sys


def serve(requests, replies) -> None:
    from .tts import VOICE_MODEL, _make_synth_config, load_voice, synthesize_to_file
    voices = {VOICE_MODEL: load_voice()}
    list(voices[VOICE_MODEL].synthesize("purple.", _make_synth_config()))
    print("ready", file=replies, flush=True)
    for line in requests:
        wav_path, _, rest = line.rstrip("\n").partition("\t")
        text, _, model = rest.partition("\t")
        model = model or VOICE_MODEL
        try:
            if model not in voices:
                voices[model] = load_voice(model)
            ok = synthesize_to_file(voices[model], text, wav_path, model)
        except Exception:
            ok = False
        print("ok" if ok else "fail", file=replies, flush=True)


if __name__ == "__main__":
    replies, sys.stdout = sys.stdout, sys.stderr  # stray prints must never reach the protocol pipe
    serve(sys.stdin, replies)
