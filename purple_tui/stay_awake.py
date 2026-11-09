"""`stay-awake` in the Parent Menu terminal turns off Purple's idle sleep face and auto-shutdown
until `stay-awake off` or a restart. Lid-close shutdown still applies."""

import sys
from pathlib import Path

FLAG = Path("/tmp/purple-stay-awake")


def is_on() -> bool:
    return FLAG.exists()


def main(args: list[str]) -> int:
    if args == ["off"]:
        FLAG.unlink(missing_ok=True)
        print("Purple will go to sleep and turn off on its own again.")
    elif not args:
        FLAG.touch()
        print("Purple will stay awake until it restarts: no sleeping face, no turning off on its own.\n"
              "Closing the lid still turns it off. Type stay-awake off to undo.")
    else:
        print("Type stay-awake to keep Purple awake, or stay-awake off to undo.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
