# Purple Computer

> **Raw URL for LLM context:** https://raw.githubusercontent.com/purplecomputerorg/purplecomputer/refs/heads/main/CONTEXT.md

**A joyful, kid-safe creativity computer built from your old laptop.**

Purple Computer is a calm, distraction-free computing environment for kids. Designed for ages 3-10, from learning letters to writing code. It transforms old laptops into magical creativity machines where every keystroke brings wonder and mistakes are impossible.

## The Vision

Purple Computer is a creativity device, not an entertainment device. Kids write, draw, explore, type, and imagine, slowly and calmly. There are no videos, no ads, no app stores, no infinite feeds, no accounts, no tracking, no social media, and no algorithms.

**Screen time that feels like quiet time.**

For screen-skeptical parents: a computer kids can't break, and parents don't have to fight with.

## Sustainability

**Every Purple Laptop saves a device from the landfill.**

Purple Computer runs on 2010-2020 era laptops: ThinkPads, Dell Latitudes, HP EliteBooks, Surfaces, MacBook Airs. These machines have years of life left but often sit in drawers or head to e-waste. Purple gives them new purpose as dedicated creativity tools for kids, extending their lifespan by 5-10 more years.

Minimal requirements: 2GB RAM, 16GB storage, 1024×768 display, x86_64 processor. Old hardware runs it beautifully.

## The Three Rooms

Purple Computer organizes around three simple rooms. Tap Escape to open the room picker and move between them.

### Play
A math and word playground. Type `2 + 2` and see `4`. Type `cat` and see 🐱. Type `cat + dog` and see 🐱🐶. Type `3 * rainbow` and see 🌈🌈🌈. Mix colors: `red + blue` shows purple. Purple can read any word out loud. Every word becomes an opportunity for delight.

### Music
Every letter plays a note. Record a loop with Space, then play along with it. Enter swaps instruments, Left/Right shift the musical key, Up/Down shift the octave, and Letters mode names each letter aloud as it's pressed. No wrong notes, just exploration.

### Art
Draw or write anything with colors and letters. Every letter paints its own color, and you can mix them like real paint. Steer the paintbrush with the arrow keys, or just mash on the keys and see what happens.

### Code Space
When they're ready, real code. In Music or Art, hold Space to open Code Space and write Logo-turtle-style programs like `repeat 4: forward 10 green turn`.

## Key Design Principles

- **No files to delete, no settings to break, no internet to worry about**
- **No login required**: boots straight into the purple interface
- **Offline by default**: works without network access
- **One-handed typing friendly**: sticky shift and double-tap for capitals
- **Parent mode** (hold Escape 1s): opens admin menu for shell access

## Getting a Purple Computer

Purple Computer is designed to be dead simple for non-technical parents. You buy a Purple Key: a USB drive that turns your old laptop into Purple.

1. We mail you a Purple Key (and a few goodies like keyboard stickers).
2. Plug it into your old laptop, restart, and pick Purple from the boot menu.
3. Purple starts up right from the Purple Key. Hand it over.

Nothing on your laptop is changed: Purple runs live from the Purple Key, so you can plug it in whenever you like. When you're ready, you can install it permanently from the parent menu. One purchase covers as many laptops as you like, now or later.

Because Purple is open source, you can also build a Purple Key yourself from the source code instead of buying one.

## Technology

Purple Computer is a custom Linux-based operating system built on Ubuntu 24.04 LTS. The interface is a fullscreen terminal application (Python + Textual) running in Alacritty with:

- Large, kid-appropriate text sizing (auto-calculated to the largest font that fits the screen)
- Text-to-speech for typed content (Piper TTS, works offline)
- Custom keyboard handling for young typists (sticky shift, double-tap capitals), read directly from evdev with keyd remaps at the kernel level
- Kid-proof power: button tap shows sleep screen, hold 3s shuts down; lid close shuts down after 10 min
- Trackpad/mouse disabled (keyboard only)

The entire experience fits in a 134×29 character viewport, filling most of the screen on typical 11-15" donated laptops.

## Content Packs

Purple uses a modular content pack system. Packs contain emojis, sounds, and definitions, no executable code. The core pack includes 350+ emojis with kid-friendly short names.

## Who It's For

- **Kids ages 3-10** (from learning letters to writing code) who are ready for screen time that sparks creativity
- **Parents** who want safe, calm, educational screen time
- **Families** with old laptops gathering dust
- **Anyone** who believes computing can be joyful, accessible, and magical
