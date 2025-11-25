# Purple Computer Architecture

## Overview

Purple Computer is a kid-friendly, educational computing environment with a modular architecture supporting packs, updates, and parent-controlled management.

## Core Principles

1. **Simplicity** - Minimal dependencies, easy to understand
2. **Safety** - No network by default, parent-controlled features
3. **Modularity** - Content packaged as installable packs
4. **Extensibility** - Easy to add new emoji, modes, and features
5. **Offline-first** - Works perfectly without internet

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Purple Computer                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │   Kid Mode   │  │ Parent Mode │  │  Updates  │ │
│  │              │  │             │  │           │ │
│  │  IPython     │  │  Password   │  │  HTTPS    │ │
│  │  REPL        │  │  Protected  │  │  Fetch    │ │
│  └──────┬───────┘  └──────┬──────┘  └─────┬─────┘ │
│         │                 │                │       │
│         └─────────────────┴────────────────┘       │
│                           │                        │
│                  ┌────────▼────────┐               │
│                  │  Pack Registry  │               │
│                  │                 │               │
│                  │  - Emoji        │               │
│                  │  - Definitions  │               │
│                  │  - Modes        │               │
│                  │  - Sounds       │               │
│                  └────────┬────────┘               │
│                           │                        │
│         ┌─────────────────┴─────────────────┐     │
│         │                                    │     │
│  ┌──────▼────────┐               ┌──────────▼───┐ │
│  │ Pack Manager  │               │  Pack Loader │ │
│  │               │               │              │ │
│  │ - Install     │               │ - Validation │ │
│  │ - Uninstall   │               │ - Loading    │ │
│  │ - List        │               │ - Registry   │ │
│  └───────────────┘               └──────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              File System Structure                  │
├─────────────────────────────────────────────────────┤
│  /home/purple/                                      │
│    .purple/                                         │
│      ├── repl.py              (Main REPL)          │
│      ├── pack_manager.py      (Pack system)        │
│      ├── parent_auth.py       (Auth system)        │
│      ├── update_manager.py    (Updates)            │
│      ├── parent.json          (Parent password)    │
│      ├── packs/               (Installed packs)    │
│      │   ├── core-emoji/                           │
│      │   └── education-basics/                     │
│      └── modes/               (Legacy modes)       │
│                                                     │
│    .config/kitty/kitty.conf   (Terminal config)    │
│    .xinitrc                   (X11 startup)        │
│    .bash_profile              (Auto-startx)        │
│    .ipython/                  (IPython config)     │
│      └── profile_default/                          │
│          └── startup/         (Startup scripts)    │
│              ├── 10-emoji.py                       │
│              └── 20-mode_manager.py                │
└─────────────────────────────────────────────────────┘
```

## Component Details

### 1. REPL (repl.py)

**Purpose:** Main entry point for Purple Computer

**Responsibilities:**
- Initialize IPython environment
- Load packs at startup
- Register parent mode escape handler
- Configure prompts and appearance

**Key Functions:**
- `main()` - Entry point
- `create_config()` - IPython configuration
- `install_parent_escape()` - Parent mode handler
- `show_parent_menu()` - Parent mode interface

### 2. Pack Manager (pack_manager.py)

**Purpose:** Manage content packs

**Classes:**
- `PackRegistry` - Central registry for all pack content
- `PackManager` - Install, uninstall, and load packs

**Capabilities:**
- Install `.purplepack` files
- Validate pack manifests
- Load pack content into registry
- Track installed pack versions
- Verify file integrity

**Security:**
- Path traversal protection
- Manifest validation
- Hash verification (optional)
- Graceful error handling

### 3. Parent Auth (parent_auth.py)

**Purpose:** Password protection for parent mode

**Class:** `ParentAuth`

**Features:**
- Password hashing (SHA256 + salt)
- First-run setup
- Password hints
- Change password
- Reset password
- Attempt limiting (3 attempts)

**Storage:** `~/.purple/parent.json` (permissions 600)

### 4. Update Manager (update_manager.py)

**Purpose:** Fetch and install updates

**Class:** `UpdateManager`

**Capabilities:**
- Fetch JSON update feed
- Compare versions (semantic versioning)
- Download packs and core files
- Verify SHA256 hashes
- Install via pack manager
- Track installed versions

**Security:**
- HTTPS only
- Hash verification
- No telemetry or tracking
- Parent authentication required

### 5. Pack System

**Pack Types:**
- **emoji** - Variable name → emoji mappings
- **definitions** - Word → definition mappings
- **mode** - Python mode classes
- **sounds** - Audio files (WAV, OGG, MP3)
- **mixed** - Combination of above

**Pack Format:**
```
pack.purplepack (tar.gz)
├── manifest.json
└── content/
    ├── emoji.json
    ├── definitions.json
    ├── modes/
    └── sounds/
```

**Manifest Schema:**
```json
{
  "id": "unique-pack-id",
  "name": "Display Name",
  "version": "1.0.0",
  "type": "emoji|definitions|mode|sounds|mixed",
  "description": "Optional description",
  "author": "Optional author"
}
```

### 6. Registry System

**Purpose:** Centralized content access

The `PackRegistry` provides:
- `get_emoji(name)` - Lookup emoji
- `get_all_emoji()` - All emoji as dict
- `get_definition(word)` - Lookup definition
- `get_mode(name)` - Lookup mode class
- `list_packs()` - List installed packs

**Usage in REPL:**
```python
from pack_manager import get_registry

registry = get_registry()
cat_emoji = registry.get_emoji('cat')
```

## Data Flow

### Startup Flow

```
1. User logs in (auto-login, no password)
   ↓
2. .bash_profile runs → startx
   ↓
3. .xinitrc runs → kitty
   ↓
4. Kitty runs → python3 ~/.purple/repl.py
   ↓
5. repl.py initializes:
   - Create PackRegistry
   - Create PackManager
   - Load all packs from ~/.purple/packs/
   - Install parent escape handler
   - Start IPython
   ↓
6. IPython runs startup scripts:
   - 10-emoji.py loads emoji from registry
   - 20-mode_manager.py loads modes
   ↓
7. Kid sees: 💜 prompt
```

### Pack Installation Flow

```
1. Parent presses Ctrl+C
   ↓
2. Parent enters password
   ↓
3. Parent selects "Install packs"
   ↓
4. Parent provides pack path
   ↓
5. PackManager.install_pack_from_file():
   - Extract to temp directory
   - Validate manifest
   - Check for path traversal
   - Move to ~/.purple/packs/<pack-id>/
   - Load pack content into registry
   ↓
6. Content immediately available
```

### Update Flow

```
1. Parent selects "Check for updates"
   ↓
2. UpdateManager.check_for_updates():
   - Fetch feed JSON over HTTPS
   - Compare versions with installed
   - Return list of available updates
   ↓
3. Parent confirms installation
   ↓
4. UpdateManager.install_all_updates():
   - For each update:
     - Download pack file
     - Verify SHA256 hash
     - Install via PackManager
     - Update version tracking
   ↓
5. Packs loaded and ready
```

## Security Model

### Threat Model

**Protected Against:**
- Kids accessing system settings ✓
- Accidental changes to configuration ✓
- Unauthorized pack installation ✓
- Unauthorized updates ✓

**Not Protected Against:**
- Physical access to computer
- Booting from USB
- TTY switching (Ctrl+Alt+F2)
- Determined tech-savvy older kids

### Password Policy

**System Password:** NONE
- `purple` user account is locked
- No password login possible
- Auto-login on TTY1 only

**Parent Password:** Required for parent mode
- Separate from system password
- Stored in `~/.purple/parent.json`
- Hashed with SHA256 + unique salt
- Created on first parent mode access
- 4 character minimum (8-10 recommended)

### Network Security

- **Default:** Network disabled
- **Optional:** Enable via parent mode
- **Updates:** HTTPS only
- **Verification:** SHA256 hashes

## Modular Design

### Adding a New Pack Type

1. Update `pack_manager.py`:
```python
valid_types = ['emoji', 'definitions', 'mode', 'sounds', 'mixed', 'mynewtype']
```

2. Add registry storage:
```python
class PackRegistry:
    def __init__(self):
        self.mynewtype_data: Dict = {}

    def add_mynewtype(self, key, value, pack_id):
        self.mynewtype_data[key] = value
```

3. Add loader in `PackManager.load_pack()`:
```python
if pack_type in ['mynewtype', 'mixed']:
    data_file = content_dir / 'mynewtype.json'
    if data_file.exists():
        # Load and register
```

### Adding a New Parent Mode Menu Option

Edit `purple_repl/repl.py`:

```python
def show_parent_menu():
    print("10. My new option")

    # In choice handler:
    elif choice == '10':
        my_new_function()
```

### Creating a New Mode

Create a mode file:

```python
# purple_repl/modes/mymode.py
class MyMode:
    def __init__(self):
        self.name = "My Mode"

    def activate(self):
        print("✨ My Mode activated!")
```

Register in `autoinstall/files/ipython/20-mode_manager.py`:

```python
from modes.mymode import MyMode

def mymode():
    global _current_mode
    _current_mode = MyMode()
    _current_mode.activate()
```

## Extension Points

### For Users

- Install emoji packs
- Install definition packs
- Install sound packs
- Create custom packs
- Share packs with community

### For Developers

- Create new modes (Python)
- Create pack builder tools
- Host custom update feeds
- Contribute to core

### For Schools/Organizations

- Deploy with custom pack set
- Host internal update feed
- Customize parent mode options
- Pre-configure settings

## Performance Considerations

### Startup Time

**Target:** < 5 seconds from power-on to REPL

**Optimizations:**
- Minimal package set (no full desktop environment)
- Fast boot (GRUB timeout = 1s)
- Auto-login (no login prompt)
- Cached pack loading
- Lazy mode initialization

### Memory Usage

**Target:** < 500 MB RAM

**Current:**
- Base system: ~200 MB
- X11 + Kitty: ~100 MB
- IPython: ~50 MB
- Packs: ~10 MB
- Total: ~360 MB

### Storage

**Minimal Install:** ~2 GB
- Ubuntu minimal: ~1.5 GB
- Purple Computer: ~50 MB
- Packs: ~10 MB each
- Cache: ~50 MB

**Recommended:** 16 GB for comfort

## Future Enhancements

### Planned Features

- [ ] Actual Ctrl+Alt+P hotkey (not just Ctrl+C)
- [ ] Multiple update feeds
- [ ] Pack dependency resolution
- [ ] Update scheduling/automation
- [ ] Visual pack browser
- [ ] Pack ratings/reviews
- [ ] Network status indicator
- [ ] Session recording for parents
- [ ] Time limits and parental controls
- [ ] Multi-user support

### Potential Improvements

- WebAssembly-based modes
- Voice command support
- Touch screen support
- Hardware device integration
- Remote management API
- Cloud backup/sync
- Educational progress tracking

## Testing

### Manual Testing

```bash
# Test pack installation
./scripts/build_pack.py packs/core-emoji packs/test.purplepack
python3 -c "
from pack_manager import PackManager, get_registry
from pathlib import Path
mgr = PackManager(Path('/tmp/test'), get_registry())
print(mgr.install_pack_from_file(Path('packs/test.purplepack')))
"

# Test parent auth
python3 -c "
from parent_auth import ParentAuth
from pathlib import Path
auth = ParentAuth(Path('/tmp/test-auth.json'))
auth.set_password('test1234', 'test hint')
print(auth.verify_password('test1234'))
"

# Test updates
python3 -c "
from update_manager import UpdateManager
from pathlib import Path
mgr = UpdateManager('https://example.com/feed.json', Path('/tmp/packs'))
success, updates = mgr.check_for_updates()
print(f'Success: {success}, Updates: {len(updates)}')
"
```

### Automated Testing

Currently manual. Future: unit tests, integration tests, ISO testing in QEMU.

## Deployment

### Installation Methods

1. **ISO Installation** - Automated Ubuntu install with autoinstall.yaml
2. **Manual Setup** - Run setup.sh on existing Ubuntu system
3. **Source Install** - Copy purple_repl files manually

### Configuration Management

- `autoinstall.yaml` - ISO installation configuration
- `setup.sh` - Manual installation script
- `~/.purple/` - User configuration and data

## Documentation

- `README.md` - Project overview
- `docs/packs.md` - Pack creation guide
- `docs/updates.md` - Update system guide
- `docs/parent-mode.md` - Parent mode documentation
- `docs/architecture.md` - This document
- `docs/autoinstall.md` - ISO building guide
- `docs/dev.md` - Development guide

---

Purple Computer: Simple, safe, and extensible computing for kids! 💜
