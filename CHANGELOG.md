# Changelog

All notable changes to Purple Computer will be documented in this file.

## [2.0.0] - 2025-11-25

### Major Architecture Refactor

This release introduces a complete overhaul of Purple Computer's architecture with a focus on modularity, security, and extensibility.

### Added

#### Pack System
- **Modular Content Packs**: Install emoji, definitions, modes, and sounds as `.purplepack` files
- **Pack Manager**: Install, uninstall, and manage content packs
- **Pack Registry**: Centralized registry for all pack content
- **Pack Builder Script**: `scripts/build_pack.py` for creating packs
- **Example Packs**:
  - `core-emoji.purplepack` - 100+ emoji with short variable names
  - `education-basics.purplepack` - Computer science definitions for kids

#### Parent Mode
- **Password-Protected Parent Mode**: Secure access to system settings
- **Parent Authentication**: Separate password system (not system password)
- **Parent Password Storage**: SHA256 hashed with unique salt in `~/.purple/parent.json`
- **First-Run Setup**: Prompts to create parent password on first access
- **Password Hints**: Optional password hints for recovery
- **Enhanced Menu**: 9 options including updates, packs, password management

#### Update System
- **Update Manager**: Check for and install updates over HTTPS
- **Update Feed**: Fetch JSON feed listing available updates
- **Version Tracking**: Track installed pack and core file versions
- **Hash Verification**: SHA256 hash checking for downloaded files
- **Semantic Versioning**: Proper version comparison
- **Offline Support**: Updates are optional, system works fully offline

#### Security
- **No System Password**: `purple` user auto-logs in with locked password
- **Parent Password Only**: Separate password protects parent-only features
- **Legacy Support**: `kiduser` account created for backwards compatibility
- **Locked Accounts**: Both `purple` and `kiduser` accounts have locked passwords

### Changed

#### User Accounts
- **Primary User**: Changed from `kiduser` to `purple`
- **Auto-Login**: System uses auto-login, no password prompt
- **Password Removal**: Removed hardcoded system password from setup.sh
- **Backwards Compatibility**: `kiduser` still created for existing setups

#### REPL Architecture
- **Registry-Based**: Emoji and content loaded from pack registry
- **Pack Loading**: Packs loaded at startup
- **Modular Startup**: IPython startup scripts load from registry
- **Error Logging**: Pack errors logged to `~/.purple/pack_errors.log`

#### Installation
- **Updated autoinstall.yaml**: No system password, pack directories created
- **Updated setup.sh**: Creates `purple` user, no password, packs support
- **Python Dependencies**: Added `packaging` for version comparison

### Documentation

- **NEW: docs/architecture.md** - Complete system architecture guide
- **NEW: docs/packs.md** - Pack creation and management guide
- **NEW: docs/updates.md** - Update system documentation
- **NEW: docs/parent-mode.md** - Parent mode guide and security model
- **Updated: README.md** - Reflects new features and architecture
- **Updated: docs/autoinstall.md** - Updated password policy

### Technical Details

#### New Modules
- `purple_repl/pack_manager.py` - Pack management and registry (370 lines)
- `purple_repl/parent_auth.py` - Parent authentication system (250 lines)
- `purple_repl/update_manager.py` - Update fetching and installation (280 lines)
- `scripts/build_pack.py` - Pack builder utility (90 lines)

#### Modified Files
- `purple_repl/repl.py` - Added parent mode menu, pack loading, update integration
- `autoinstall/files/ipython/10-emoji.py` - Load emoji from registry instead of hardcoded
- `autoinstall/files/setup.sh` - Remove password, create packs directories
- `autoinstall/autoinstall.yaml` - Update for new user model and password policy

#### Pack Format
- `.purplepack` files are tar.gz archives
- Contain `manifest.json` and `content/` directory
- Support types: emoji, definitions, mode, sounds, mixed
- Manifest requires: id, name, version, type

#### Security Model
- System password: NONE (account locked)
- Parent password: Required for parent mode
- Password storage: SHA256 + salt in `~/.purple/parent.json` (600 permissions)
- Network: Disabled by default, optional via parent mode
- Updates: HTTPS only, SHA256 verification

### Migration Notes

**For existing Purple Computer installations:**

1. Run the updated `setup.sh` script to:
   - Create the `purple` user
   - Set up pack directories
   - Install new Python modules

2. The `kiduser` account will continue to work (backwards compatible)

3. Parent mode password needs to be set on first access

4. Existing emoji will continue to work via fallback in 10-emoji.py

**For fresh installations:**

- System uses `purple` user by default
- No password required (auto-login)
- Parent password set on first parent mode access
- Core packs can be pre-installed

### Breaking Changes

- System username changed from `kiduser` to `purple` (with backwards compatibility)
- Hardcoded emoji in 10-emoji.py replaced with registry-based loading
- Parent mode now requires password authentication
- Update feeds expected at `https://purplecomputer.org/updates/feed.json` (customizable)

### Deprecations

- Direct emoji hardcoding in startup files (use packs instead)
- Hardcoded system passwords (use parent password only)

### Known Issues

- Ctrl+Alt+P hotkey not yet implemented (use Ctrl+C for now)
- Pack dependencies not yet supported
- Automatic update checking not implemented
- No GUI pack installer (command-line only)

### Future Enhancements

See docs/architecture.md for planned features including:
- Actual Ctrl+Alt+P hotkey implementation
- Multiple update feeds
- Pack dependency resolution
- Visual pack browser
- Session recording
- Time limits and parental controls

---

## [1.0.0] - 2025-11-25

### Initial Release

- Basic IPython REPL environment
- Hardcoded emoji variables
- Speech modes
- Big letter mode
- Auto-login with hardcoded password
- Basic parent escape menu
- Ubuntu autoinstall configuration
- X11 + Kitty terminal setup

---

For upgrade instructions, see [docs/updates.md](docs/updates.md)
