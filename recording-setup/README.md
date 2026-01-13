# Recording Setup

Tools for recording Purple Computer demo screencasts in a VM.

## Quick Start

In your Ubuntu VM:

```bash
# 1. Install recording tools (one-time)
make recording-setup

# 2. Record the demo
make record-demo
```

The recording will be saved to `recordings/demo.mp4`.

## How It Works

1. **FFmpeg** captures the X11 display at 30fps
2. **Purple Computer** starts with `PURPLE_DEMO_AUTOSTART=1`
3. The demo script (`purple_tui/demo/default_script.py`) plays automatically
4. Recording stops when you exit Purple (Ctrl+C or demo finishes)

## Customizing the Demo

Edit `purple_tui/demo/default_script.py` to change what the demo shows.

The script uses simple actions:

```python
TypeText("Hello World!")      # Type characters
PressKey("enter")             # Press special keys
SwitchMode("play")            # Switch to F2 mode
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
make run-demo
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

**No sound in recording**: FFmpeg x11grab doesn't capture audio. Record audio separately or add it in post.
