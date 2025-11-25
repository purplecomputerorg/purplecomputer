# Purple Computer Packs

Packs are modular content bundles that extend Purple Computer with new emoji, definitions, modes, and sounds.

## What are Packs?

Packs allow you to:
- Add new emoji that kids can use
- Provide definitions for learning new words
- Add custom interaction modes
- Include sound effects or music
- Mix any of the above

Packs are distributed as `.purplepack` files - simple compressed archives that can be installed manually or via the update system.

## Pack Types

Purple Computer supports these pack types:

- **emoji** - Collections of emoji with short variable names
- **definitions** - Word definitions for learning
- **mode** - Custom interaction modes (requires Python code)
- **sounds** - Audio files for sound effects or music
- **mixed** - Combines multiple types in one pack

## Pack Structure

A `.purplepack` file is a gzipped tar archive containing:

```
my-pack.purplepack
├── manifest.json       (required)
└── content/           (optional)
    ├── emoji.json
    ├── definitions.json
    ├── sounds/
    │   ├── beep.wav
    │   └── boop.ogg
    └── modes/
        └── mymode.py
```

### Manifest Format

Every pack must have a `manifest.json`:

```json
{
  "id": "my-awesome-pack",
  "name": "My Awesome Pack",
  "version": "1.0.0",
  "type": "emoji",
  "description": "A collection of awesome emoji!",
  "author": "Your Name"
}
```

**Required fields:**
- `id` - Unique identifier (lowercase, hyphens only)
- `name` - Human-readable name
- `version` - Semantic version (x.y.z format)
- `type` - One of: emoji, definitions, mode, sounds, mixed

**Optional fields:**
- `description` - What the pack provides
- `author` - Who created it
- `url` - Homepage or repository URL
- `license` - License (default: MIT)

### Emoji Packs

Emoji packs provide `content/emoji.json`:

```json
{
  "unicorn": "🦄",
  "dragon": "🐉",
  "fairy": "🧚",
  "castle": "🏰",
  "magic": "✨"
}
```

Each key becomes a variable accessible in Purple Computer.

### Definition Packs

Definition packs provide `content/definitions.json`:

```json
{
  "unicorn": "A magical horse with a horn on its head",
  "dragon": "A large mythical creature that breathes fire",
  "fairy": "A tiny magical being with wings"
}
```

Kids can look up definitions by typing the word.

### Mode Packs

Mode packs include Python code in `content/modes/`:

```python
# content/modes/mymode.py
class MyMode:
    def __init__(self):
        self.name = "My Mode"

    def activate(self):
        print("✨ My Mode activated!")
```

Modes are loaded automatically and registered in the REPL.

### Sound Packs

Sound packs include audio files in `content/sounds/`:

```
content/sounds/
  ├── beep.wav
  ├── boop.ogg
  └── melody.mp3
```

Supported formats: WAV, OGG, MP3

## Creating a Pack

### Method 1: Using the Builder Script

1. Create your pack source directory:

```bash
mkdir my-pack
cd my-pack
```

2. Create `manifest.json`:

```json
{
  "id": "my-pack",
  "name": "My Pack",
  "version": "1.0.0",
  "type": "emoji"
}
```

3. Create content:

```bash
mkdir content
echo '{"star": "⭐", "moon": "🌙"}' > content/emoji.json
```

4. Build the pack:

```bash
./scripts/build_pack.py my-pack my-pack.purplepack
```

### Method 2: Manual Creation

```bash
# Create structure
mkdir -p pack-source/content
cd pack-source

# Add manifest
cat > manifest.json <<EOF
{
  "id": "example",
  "name": "Example Pack",
  "version": "1.0.0",
  "type": "emoji"
}
EOF

# Add content
cat > content/emoji.json <<EOF
{
  "example": "📦"
}
EOF

# Create archive
tar czf ../example.purplepack manifest.json content/
```

## Installing Packs

### Via Parent Mode

1. Press Ctrl+C (or Ctrl+Alt+P) to enter parent mode
2. Enter parent password
3. Select "Install packs" (option 3)
4. Enter the path to your `.purplepack` file
5. Pack is installed and loaded immediately

### Via Command Line

```python
from pathlib import Path
from pack_manager import PackManager, get_registry

packs_dir = Path.home() / '.purple' / 'packs'
registry = get_registry()
manager = PackManager(packs_dir, registry)

success, msg = manager.install_pack_from_file(Path('mypack.purplepack'))
print(msg)
```

### Via Updates

Packs can be distributed via the update feed (see updates.md).

## Listing Installed Packs

In parent mode, select "List installed packs" (option 4) to see all packs.

Or programmatically:

```python
from pack_manager import get_registry

registry = get_registry()
for pack in registry.list_packs():
    print(f"{pack['name']} v{pack['version']}")
```

## Example Packs

Purple Computer includes these core packs:

### Core Emoji Pack

Essential emoji for everyday use:

```bash
ls packs/core-emoji.purplepack
```

Contains 100+ emoji across categories: animals, nature, food, objects, faces, symbols.

### Education Basics Pack

Computer science and coding definitions for learning:

```bash
ls packs/education-basics.purplepack
```

Includes definitions for: computer, code, program, bug, variable, function, loop, and more.

## Pack Best Practices

### Keep Packs Focused

One pack = one purpose. Don't mix unrelated content.

**Good:**
- "Space Emoji Pack" - rockets, planets, stars, astronauts
- "Animal Sounds Pack" - meow.wav, woof.wav, roar.wav

**Bad:**
- "Random Stuff Pack" - some emoji, some sounds, some definitions

### Use Semantic Versioning

- `1.0.0` - Initial release
- `1.1.0` - Added new content (backwards compatible)
- `2.0.0` - Changed emoji names or removed content (breaking)

### Test Your Pack

```python
# Test installing locally
./scripts/build_pack.py my-pack test.purplepack

# Install in a test environment
python3 <<EOF
from pack_manager import PackManager, get_registry
from pathlib import Path

manager = PackManager(Path('/tmp/test-packs'), get_registry())
success, msg = manager.install_pack_from_file(Path('test.purplepack'))
print(msg)
EOF
```

### Include a README

Add a `README.md` in your pack source directory explaining:
- What the pack provides
- Who it's for (age range, skill level)
- How to use it
- Any dependencies

### Set Appropriate File Sizes

- Keep emoji packs small (< 1 MB)
- Compress audio files (use OGG instead of WAV)
- Limit definition packs to 100-200 entries

## Pack Security

Purple Computer validates packs before installation:

- Checks manifest format
- Validates file paths (no path traversal)
- Verifies hash if provided
- Ignores malformed files

**Never install packs from untrusted sources!**

## Sharing Packs

### Distribution Methods

1. **Direct file sharing** - Share `.purplepack` files via USB, email, etc.
2. **Update feed** - Host packs and list them in an update feed JSON
3. **GitHub releases** - Attach packs to release tags
4. **Website download** - Host on your own website

### Example Update Feed Entry

```json
{
  "packs": [
    {
      "id": "my-pack",
      "name": "My Pack",
      "version": "1.0.0",
      "url": "https://example.com/packs/my-pack.purplepack",
      "hash": "sha256:abc123...",
      "description": "Cool new emoji!"
    }
  ]
}
```

## Troubleshooting

### Pack Won't Install

- Check manifest.json is valid JSON
- Verify `id` doesn't contain spaces or special characters
- Ensure `version` follows x.y.z format
- Check `type` is one of the valid types

### Emoji Don't Appear

- Verify emoji.json is valid JSON
- Check emoji variable names are valid Python identifiers
- Restart Purple Computer after installing

### Mode Doesn't Load

- Check Python syntax in mode files
- Verify class name matches filename
- Look in `~/.purple/pack_errors.log` for errors

### "Pack already installed"

```python
# Uninstall first
from pack_manager import PackManager, get_registry
from pathlib import Path

manager = PackManager(Path.home() / '.purple' / 'packs', get_registry())
manager.uninstall_pack('pack-id')
```

## Advanced Topics

### Dynamic Pack Loading

Packs are loaded at Purple Computer startup. To load without restarting:

```python
from pack_manager import PackManager, get_registry
from pathlib import Path

manager = PackManager(Path.home() / '.purple' / 'packs', registry := get_registry())
manager.load_pack('pack-id')

# Access new emoji
registry.get_emoji('newemoji')
```

### Pack Dependencies

Future versions may support dependencies:

```json
{
  "id": "my-pack",
  "dependencies": {
    "core-emoji": ">=1.0.0"
  }
}
```

Currently not implemented.

### Custom Pack Types

To add custom pack types, modify `pack_manager.py`:

```python
# In PackManager.validate_manifest()
valid_types = ['emoji', 'definitions', 'mode', 'sounds', 'mixed', 'custom']
```

---

Happy pack creating! Share your packs with the Purple Computer community! 💜
