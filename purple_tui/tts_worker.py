"""Speech worker process. Loads the Piper voice once, warms it, then answers one
request per stdin line ("<wav path>\\t<prepared text>") with ok or fail.

Building the ONNX session holds the GIL for seconds, so it happens here instead
of in the UI process. Exits on stdin EOF, so it dies with the app."""

import sys


def serve(requests, replies) -> None:
    from .tts import _make_synth_config, load_voice, synthesize_to_file
    voice = load_voice()
    list(voice.synthesize("purple.", _make_synth_config()))
    print("ready", file=replies, flush=True)
    for line in requests:
        wav_path, _, text = line.rstrip("\n").partition("\t")
        try:
            ok = synthesize_to_file(voice, text, wav_path)
        except Exception:
            ok = False
        print("ok" if ok else "fail", file=replies, flush=True)


if __name__ == "__main__":
    replies, sys.stdout = sys.stdout, sys.stderr  # stray prints must never reach the protocol pipe
    serve(sys.stdin, replies)
