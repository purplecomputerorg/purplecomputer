# Purple Computer Parent Mode

Parent Mode provides password-protected access to system settings, updates, and advanced features.

## Overview

Purple Computer's security model:
- **No system password** - The `purple` user auto-logs in with no password
- **Parent password** - A separate password protects parent mode
- **Physical access assumed** - Purple Computer is a toy for supervised use
- **Kid-safe by default** - Children can't access system settings

## Accessing Parent Mode

### During Normal Use

While Purple Computer is running, press **Ctrl+C** (keyboard interrupt) to trigger parent mode.

Future versions will support **Ctrl+Alt+P** as a dedicated shortcut.

### First Time Setup

The first time you enter parent mode, you'll be prompted to create a parent password:

```
==================================================
PURPLE COMPUTER - PARENT MODE SETUP
==================================================

No parent password is set.
You need to create one to protect parent mode.

Create parent password (4+ chars): ****
Confirm password: ****
Password hint (optional, press Enter to skip): My dog's name

✓ Parent password set successfully
```

**Important:**
- Password must be at least 4 characters
- Password is stored securely (hashed with SHA256 + salt)
- Password hint is optional but recommended
- Store password safely - there's no online recovery

### Subsequent Access

After setup, you'll be prompted for your password:

```
Hint: My dog's name
Enter parent password: ****
```

You have 3 attempts. After 3 failed attempts, you're returned to Purple Computer.

## Parent Mode Menu

Once authenticated, you see the parent menu:

```
==================================================
PURPLE COMPUTER - PARENT MENU
==================================================

1. Return to Purple Computer
2. Check for updates
3. Install packs
4. List installed packs
5. Change parent password
6. Open system shell (advanced)
7. Network settings (advanced)
8. Shut down
9. Restart

Enter choice (1-9):
```

### Option 1: Return to Purple Computer

Exit parent mode and return to the kid-friendly interface.

### Option 2: Check for Updates

Fetches the update feed and displays available updates:

```
==================================================
CHECKING FOR UPDATES
==================================================

Fetching update feed...

✓ Found 2 update(s):

1. NEW: Space Emoji Pack v1.0.0
   Rockets, planets, stars, and astronauts!

2. UPDATE: Core Emoji v1.0.0 → v1.1.0
   Added 20 new animal emoji

Install all updates? (yes/no):
```

Type `yes` to install, `no` to cancel.

See [updates.md](updates.md) for details.

### Option 3: Install Packs

Install a pack from a file:

```
==================================================
INSTALL PACK FROM FILE
==================================================

Enter path to .purplepack file: /home/purple/Downloads/my-pack.purplepack

✓ Pack installed: My Pack v1.0.0

Press Enter to continue...
```

Supports:
- Absolute paths (`/path/to/pack.purplepack`)
- Relative paths (`Downloads/pack.purplepack`)
- Drag-and-drop (in GUI terminals)

See [packs.md](packs.md) for details.

### Option 4: List Installed Packs

Displays all installed packs:

```
==================================================
INSTALLED PACKS
==================================================

• Core Emoji Pack v1.1.0 (emoji)
• Education Basics Pack v1.0.0 (definitions)
• Space Theme Pack v1.0.0 (mixed)

Press Enter to continue...
```

Shows pack name, version, and type.

### Option 5: Change Parent Password

Change your parent password:

```
==================================================
CHANGE PARENT PASSWORD
==================================================

Current password: ****
New password (4+ chars): ****
Confirm new password: ****
Password hint (optional): New hint

✓ Parent password changed successfully

Press Enter to continue...
```

**Security notes:**
- Requires current password
- New password must be 4+ characters
- Updates hint if provided

### Option 6: Open System Shell (Advanced)

Opens a bash shell with full system access:

```
🔧 Opening system shell...
Type 'exit' to return to parent menu

purple@purplecomputer:~$
```

**Warning:** Advanced users only! You can:
- Run system commands
- Edit files
- Install packages
- Potentially break Purple Computer

Type `exit` to return to parent mode.

### Option 7: Network Settings (Advanced)

Placeholder for network configuration:

```
🌐 Network Settings
Use 'nmtui' to configure network (if NetworkManager is installed)

Press Enter to continue...
```

To actually configure network:

1. Select option 6 (system shell)
2. Run `sudo nmtui` (if NetworkManager installed)
3. Or manually edit `/etc/network/interfaces`

Purple Computer is designed for offline use - network is optional.

### Option 8: Shut Down

Shuts down the computer:

```
⚠️  Really shut down? (yes/no): yes

👋 Shutting down...
```

Requires explicit `yes` confirmation.

### Option 9: Restart

Restarts the computer:

```
⚠️  Really restart? (yes/no): yes

🔄 Restarting...
```

Requires explicit `yes` confirmation.

## Password Storage

Parent passwords are stored in `~/.purple/parent.json`:

```json
{
  "password_hash": "abc123...",
  "salt": "def456...",
  "hint": "My dog's name",
  "first_run": false
}
```

**Security details:**
- Password is hashed with SHA256
- Unique random salt per installation
- Hash is hex-encoded
- File permissions are 600 (owner only)

**Never share or commit this file!**

## Password Recovery

If you forget your parent password:

### Option 1: Reset via File System

1. Boot into recovery mode or live USB
2. Mount Purple Computer's drive
3. Delete `~/.purple/parent.json`
4. Reboot - you'll be prompted to create a new password

### Option 2: Reset via System Shell

If you can access a shell (TTY2, SSH, etc.):

```bash
rm ~/.purple/parent.json
```

Next parent mode access will prompt for a new password.

### Option 3: Programmatic Reset

If you can run Python:

```python
from parent_auth import get_auth

auth = get_auth()
auth.reset_password()
print("Password reset!")
```

**Note:** All options require physical access to the computer.

## Security Model

### What Parent Mode Protects

- ✅ System settings (updates, packs, network)
- ✅ Shutdown/restart
- ✅ Shell access
- ✅ Configuration changes

### What It Doesn't Protect

- ❌ Booting from USB (physical access)
- ❌ Hard drive removal (physical access)
- ❌ TTY switching (Ctrl+Alt+F2)
- ❌ Power button (physical access)

Purple Computer assumes **physical security**. It's a toy for supervised kids, not a secure workstation.

### Threat Model

**Protected against:**
- Kids accidentally changing settings
- Kids installing random files
- Kids accessing the internet unsupervised
- Kids shutting down the computer

**Not protected against:**
- Determined older kids with computer knowledge
- Physical attacks (USB boot, drive theft)
- Unsupervised physical access

**Solution:** Supervise computer use and keep it in a common area.

## Best Practices

### Choose a Strong Password

- Use at least 8-10 characters (minimum is 4)
- Mix letters and numbers
- Don't use obvious words ("password", "purple", "1234")
- Don't use kid's name or birthdate

### Use a Password Hint

- Makes recovery easier if you forget
- Keep it meaningful to you but not obvious
- Examples: "Where we got married", "Mom's middle name"

### Don't Share Your Password

- Parent mode is for parents only
- Don't tell older kids, even if they promise to behave
- If kids know the password, change it

### Exit Parent Mode When Done

- Don't leave parent mode open and walk away
- Always select "Return to Purple Computer" when finished
- Kids shouldn't see parent mode operations

### Back Up Your Password

- Write it down and store securely
- Keep in a password manager
- Share with your co-parent/guardian

### Disable Auto-login on TTY2+ (Optional)

If you want extra security:

```bash
# Disable auto-login on other TTYs
sudo systemctl disable getty@tty2.service
sudo systemctl disable getty@tty3.service
# etc.
```

Now TTY2+ will require the system password (which doesn't exist), preventing TTY switching.

## Customizing Parent Mode

### Add Custom Menu Options

Edit `purple_repl/repl.py` and modify `show_parent_menu()`:

```python
print("10. My custom option")

# In the choice handler
elif choice == '10':
    my_custom_function()
```

### Change Password Requirements

Edit `purple_repl/parent_auth.py`:

```python
# In ParentAuth.set_password()
if not password or len(password) < 10:  # Require 10+ chars
    return False, "Password must be at least 10 characters"
```

### Change Max Attempts

Edit `purple_repl/parent_auth.py`:

```python
# In ParentAuth.prompt_for_password()
def prompt_for_password(self, prompt="Enter parent password: ", max_attempts=5):
    # Now allows 5 attempts instead of 3
```

### Disable Parent Password (Not Recommended)

If you want open access to parent mode:

Edit `purple_repl/parent_auth.py`:

```python
def verify_password(self, password: str) -> bool:
    return True  # Always allow access
```

**Warning:** This defeats the purpose of parent mode!

## Troubleshooting

### "No module named 'parent_auth'"

The parent_auth module isn't installed. Run:

```bash
# Copy Purple Computer files
cd /path/to/purplecomputer
sudo ./autoinstall/files/setup.sh
```

### Can't Remember Password

See "Password Recovery" section above.

### Parent Mode Doesn't Activate

Try these:

1. Press Ctrl+C again
2. Check if REPL is actually running
3. Look for errors in `~/.purple/pack_errors.log`
4. Try from TTY2 shell instead

### Parent Password Prompt Doesn't Appear

Check if `~/.purple/parent.json` exists:

```bash
ls -la ~/.purple/parent.json
```

If missing, parent mode will prompt you to create one.

### "Access denied" Even with Correct Password

- Check caps lock isn't on
- Verify you're using the current password (not an old one)
- Try resetting password (see Password Recovery)

## API Reference

For developers integrating parent authentication:

```python
from parent_auth import get_auth

auth = get_auth()

# Check if password is set
if auth.has_password():
    print("Password is configured")

# Check if first run
if auth.is_first_run():
    print("No password set yet")

# Set password
success, msg = auth.set_password("mypassword", hint="My hint")

# Verify password
if auth.verify_password("mypassword"):
    print("Correct!")

# Change password
success, msg = auth.change_password("oldpass", "newpass", "New hint")

# Get hint
hint = auth.get_hint()

# Reset (delete password)
auth.reset_password()

# Prompt user for password
if auth.prompt_for_password():
    print("Authenticated!")
```

---

Parent Mode keeps Purple Computer safe and manageable! 💜🔒
