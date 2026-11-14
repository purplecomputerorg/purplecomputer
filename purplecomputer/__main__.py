"""Entry point so `python -m purplecomputer` loads the app module exactly once.

Running `python -m purplecomputer.app` would register the same file twice
in sys.modules (as `__main__` and as `purplecomputer.app`), giving us two
copies of every class and module-level global.
"""

from purplecomputer.app import main

if __name__ == "__main__":
    main()
