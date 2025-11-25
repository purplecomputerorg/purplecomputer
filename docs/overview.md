# Purple Computer Overview

## What is Purple Computer?

Purple Computer is an operating system for young children (ages 3-8) learning to use a computer. Instead of a desktop with icons and windows, they get a fullscreen terminal with colors, emojis, and text they can interact with directly.

## The Experience

When you turn on a Purple Computer:

1. **Fast Boot**: The computer starts up quickly
2. **Purple Welcome**: A big, friendly purple screen appears with large text
3. **Simple Instructions**: Kids see a welcome message they can understand
4. **Ready to Play**: They can start typing immediately

## What Can Kids Do?

### Talk to the Computer
Kids can type words and hear them spoken aloud. The computer has a pleasant voice that reads back what they type.

### Play with Emojis
Pre-loaded emoji variables let kids create patterns:
- `cat` → 🐱
- `dog` → 🐶
- `star` → ⭐
- `heart` → ❤️

### Switch Modes
Kids can switch between different creative modes:
- **Speech Mode**: Everything is read aloud
- **Emoji Mode**: Words turn into pictures
- **Math Mode**: Count and repeat patterns
- **Rainbow Mode**: Colorful, vibrant output
- **Surprise Mode**: Random delightful things happen

### Explore Safely
Kids can type anything without breaking the computer. There are no files to delete, no settings to mess up, no internet to wander into.

## Design Philosophy

### What It Is
Purple Computer is a text-based environment where kids type commands and see results. They control what happens by typing, not by watching or following prompts.

### Age-Appropriate (3-8 years)
- Large, readable text (18pt+)
- Simple vocabulary
- Forgiving of mistakes
- No confusing error messages
- Younger kids (3-4) explore with parents, older kids (7-8) work independently

### Safe by Default
- No access to system files
- No internet connection
- Can't exit to desktop accidentally
- Parent escape requires specific knowledge

## Technical Overview

Purple Computer is built on:
- **Ubuntu Server**: Minimal, fast Linux base
- **Kitty Terminal**: Modern, GPU-accelerated terminal
- **Python/IPython**: Powerful REPL with customization
- **Piper TTS**: High-quality offline speech synthesis
- **Systemd**: Automatic login and startup

## Parent Involvement

Parents don't need to be technical to use Purple Computer:
- Installation is automated via USB
- The system configures itself
- A simple escape mechanism lets parents regain control
- No ongoing maintenance required

See [parents.md](parents.md) for the parent guide.

## Development

Purple Computer is open source and designed to be:
- Easy to customize
- Well documented
- Simple to extend with new modes
- Reproducible from source

See [dev.md](dev.md) for developer documentation.
