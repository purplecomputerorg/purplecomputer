# Recording Setup

Tools for recording Purple Computer demo screencasts in a VM.

## Quick Start

In your Ubuntu VM:

```bash
# 1. Install recording tools (one-time)
just recording-setup

# 2. Record the demo
just record-demo
```

The recording will be saved to `recordings/demo.mp4`.

## How It Works

1. **Purple Computer** starts with `PURPLE_DEMO_AUTOSTART=1` and touches a ready-file once its UI has painted
2. **FFmpeg** then captures the X11 display at 30fps (with system audio via PulseAudio); the recorder confirms frames are flowing before touching a go-file
3. The demo script waits for the go-file, then plays; when it finishes it touches a done-file and recording stops immediately, while Purple is still on screen
4. Nothing is trimmed or re-timed, so captured audio stays perfectly aligned with video
5. **Background music** is mixed in with automatic ducking (music gets quieter when app sounds play); the video stream is stream-copied, never re-encoded
6. Set `PURPLE_RECORD_NO_POSTFX=1` to skip the cropped and zoomed versions (used by `just record-everything`)

## Background Music

Place an MP3 file at `recording-setup/demo_music.mp3` to automatically add background music.

The script uses **ducking**: music plays at ~30% volume normally, but automatically drops lower when Purple makes sounds. This keeps the app audio clear while maintaining an engaging soundtrack.

To use different music, replace `demo_music.mp3` or remove it to record without background music.

### Music Attribution

The included `demo_music.mp3` is "Happy Ukulele" by ANtarcticbreeze, licensed under [CC-BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).

Source: https://soundcloud.com/royalty-free-audio-loops/antarcticbreeze-happy-ukulele

## Customizing the Demo

Edit `purple_tui/demo/default_script.py` to change what the demo shows.

The script uses simple actions:

```python
TypeText("Hello World!")      # Type characters
PressKey("enter")             # Press special keys
SwitchRoom("play")           # Switch to the Play room
PlayKeys(['q','w','e','r'])   # Play musical notes
DrawPath(['right','down'])    # Draw with space+arrows
Pause(1.0)                    # Wait between sections
```

## Manual Recording

If you want more control:

```bash
# Record for 90 seconds to custom file
./recording-setup/record-demo.sh my-demo.mp4 90

# Or record manually while running demo
ffmpeg -video_size 1920x1080 -framerate 30 -f x11grab -i :0 output.mp4 &
just run-demo
# Press Ctrl+C to stop recording
```

## Compressing the Output

The default recording uses fast encoding for smooth capture. To compress:

```bash
# Smaller file, slower encoding
ffmpeg -i recordings/demo.mp4 -crf 23 -preset slow demo-compressed.mp4
```

## Troubleshooting

**"No DISPLAY set"**: Run from X11 session (`startx` first), not SSH.

**Choppy recording**: Close other apps, or reduce framerate to 24fps in record-demo.sh.

**No sound in recording**: Audio capture requires PulseAudio. Check that `pactl get-default-sink` returns a valid sink name. If running in a VM, ensure audio is properly configured.
